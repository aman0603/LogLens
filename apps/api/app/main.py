import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response, JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from loglens import config as ll_config
from loglens import logging as ll_logging
from loglens import health as ll_health
from loglens import metrics as ll_metrics
from loglens import auth as ll_auth
from loglens import ratelimit as ll_ratelimit
from loglens import tracing as ll_tracing

from . import crud, models, schemas, database
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient

# --- Centralized configuration (fail-fast) ---
cfg = ll_config.load_config(
    required=["DATABASE_URL", "JWT_SECRET"],
    optional={
        "QDRANT_HOST": "qdrant",
        "QDRANT_PORT": 6333,
        "QDRANT_COLLECTION": "log_collection",
        "RATE_LIMIT": 20,  # requests per second per client
        "OTEL_EXPORTER_OTLP_ENDPOINT": "",
        "EMBEDDING_MODEL": "all-MiniLM-L6-v2",
    },
    casts={"QDRANT_PORT": int, "RATE_LIMIT": int},
)

SERVICE_NAME = "api"
logger = ll_logging.get_logger(SERVICE_NAME)
secret = cfg.require("JWT_SECRET")
rate_limiter = ll_ratelimit.RateLimiter(rate=cfg.get("RATE_LIMIT"), per=1)

ll_tracing.init_tracing(SERVICE_NAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("api service starting")
    yield
    logger.info("api service shutting down")


models.Base.metadata.create_all(bind=database.engine)
app = FastAPI(title="LogLens API", lifespan=lifespan)

DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), "dashboard")
if os.path.isdir(DASHBOARD_DIR):
    app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")


# --- Dependencies ---
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Dependency callables: pass these directly to Depends(...).
require_viewer = ll_auth.require_role(["viewer", "analyst", "admin"], secret)
require_analyst = ll_auth.require_role(["analyst", "admin"], secret)


# --- Middleware: request id, rate limit, metrics ---
@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    rid = ll_logging.new_request_id()
    ll_logging.set_correlation_ids(request_id=rid)
    client = request.client.host if request.client else "unknown"
    # Rate limit only user-facing API + dashboard data, not metrics/health.
    path = request.url.path
    if path not in ("/health", "/ready", "/metrics"):
        allowed, retry_after = rate_limiter.allow(client)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(retry_after)},
            )
    start = time.time()
    try:
        response = await call_next(request)
    except Exception as e:
        ll_metrics.observe_request(SERVICE_NAME, request.method, path, 500, time.time() - start)
        logger.error("unhandled error on %s: %s", path, e)
        raise
    ll_metrics.observe_request(
        SERVICE_NAME, request.method, path, response.status_code, time.time() - start
    )
    return response


# --- Health / readiness / metrics (public) ---
@app.get("/health")
def health():
    return ll_health.health_response()


@app.get("/ready")
def ready():
    def db_ok():
        try:
            database.SessionLocal().execute("SELECT 1")
            return True
        except Exception:
            return False

    return ll_health.readiness_response({"postgres": db_ok})


@app.get("/metrics")
def metrics():
    data, ctype = ll_metrics.metrics_response()
    return Response(content=data, media_type=ctype)


# --- Dev token endpoint (portfolio/demo): exchange a known dev role for a JWT ---
@app.post("/auth/token")
def issue_token(role: str = "viewer"):
    if role not in ("viewer", "analyst", "admin"):
        raise HTTPException(status_code=400, detail="invalid role")
    token = ll_auth.create_token(secret, subject="dev", role=role, expires_sec=86400)
    return {"access_token": token, "token_type": "bearer", "role": role}


# --- Existing data APIs (now auth-protected) ---
@app.post("/logs/", response_model=schemas.LogEntryRead, dependencies=[Depends(require_viewer)])
def create_log(log: schemas.LogEntryCreate, db: Session = Depends(get_db)):
    return crud.create_log_entry(db=db, log=log)


@app.get(
    "/logs/", response_model=List[schemas.LogEntryRead], dependencies=[Depends(require_viewer)]
)
def read_logs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_logs(db, skip=skip, limit=limit)


@app.get(
    "/incidents/", response_model=List[schemas.IncidentRead], dependencies=[Depends(require_viewer)]
)
def list_incidents(
    skip: int = 0,
    limit: int = Query(100, ge=1, le=500),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return crud.get_incidents(db, skip=skip, limit=limit, status=status)


@app.get(
    "/incidents/{incident_id}",
    response_model=schemas.IncidentRead,
    dependencies=[Depends(require_viewer)],
)
def get_incident(incident_id: int, db: Session = Depends(get_db)):
    incident = crud.get_incident(db, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@app.get(
    "/incidents/{incident_id}/timeline",
    response_model=List[schemas.LogEntryRead],
    dependencies=[Depends(require_viewer)],
)
def incident_timeline(incident_id: int, db: Session = Depends(get_db)):
    incident = crud.get_incident(db, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return crud.get_logs_for_incident(db, incident)


@app.get(
    "/incidents/{incident_id}/similar",
    response_model=List[schemas.SimilarIncident],
    dependencies=[Depends(require_viewer)],
)
def similar_incidents(
    incident_id: int, limit: int = Query(5, ge=1, le=50), db: Session = Depends(get_db)
):
    incident = crud.get_incident(db, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return crud.get_similar_incidents(db, incident, limit=limit)


# Embedding model + Qdrant initialized lazily to avoid blocking startup.
EMBEDDING_MODEL = None
QDRANT_HOST = cfg.get("QDRANT_HOST")
QDRANT_PORT = cfg.get("QDRANT_PORT")
COLLECTION_NAME = cfg.get("QDRANT_COLLECTION")
EMBEDDING_MODEL_NAME = cfg.get("EMBEDDING_MODEL")
_qdrant_client = None


def _get_model():
    global EMBEDDING_MODEL
    if EMBEDDING_MODEL is None:
        EMBEDDING_MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return EMBEDDING_MODEL


def _get_qdrant():
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    return _qdrant_client


@app.get(
    "/search/", response_model=List[schemas.LogEntryRead], dependencies=[Depends(require_viewer)]
)
def semantic_search(
    q: str = Query(..., description="Natural language search query"),
    limit: int = Query(10, ge=1, le=100),
):
    vector = _get_model().encode(q).tolist()
    search_result = _get_qdrant().search(
        collection_name=COLLECTION_NAME, query_vector=vector, limit=limit
    )
    results = []
    for point in search_result:
        payload = point.payload.copy()
        payload.setdefault("id", 0)
        ts = payload.get("timestamp")
        if isinstance(ts, str):
            try:
                payload["timestamp"] = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                payload["timestamp"] = datetime.utcnow()
        elif not isinstance(ts, datetime):
            payload["timestamp"] = datetime.utcnow()
        results.append(payload)
    return results


ll_tracing.instrument_app(app, SERVICE_NAME)
