import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import Response, JSONResponse
from sqlalchemy.orm import Session

from loglens import config as ll_config
from loglens import logging as ll_logging
from loglens import health as ll_health
from loglens import metrics as ll_metrics
from loglens import auth as ll_auth
from loglens import ratelimit as ll_ratelimit
from loglens import tracing as ll_tracing

from . import investigate, schemas
from .database import SessionLocal, get_db, Incident
from .llm import LLMClient

SERVICE_NAME = "ai-service"

cfg = ll_config.load_config(
    required=["DATABASE_URL", "JWT_SECRET"],
    optional={
        "RATE_LIMIT": 20,
        "OTEL_EXPORTER_OTLP_ENDPOINT": "",
        "GEMINI_API_KEY": "",
        "LLM_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "LLM_MODEL": "gemini-3.1-flash-lite",
    },
    casts={"RATE_LIMIT": int},
)

logger = ll_logging.get_logger(SERVICE_NAME)
secret = cfg.require("JWT_SECRET")
rate_limiter = ll_ratelimit.RateLimiter(rate=cfg.get("RATE_LIMIT"), per=1)
ll_tracing.init_tracing(SERVICE_NAME)

_llm = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient(
            api_key=cfg.get("GEMINI_API_KEY"),
            base_url=cfg.get("LLM_BASE_URL"),
            model=cfg.get("LLM_MODEL"),
        )
    return _llm


# Dependency callables: pass these directly to Depends(...).
require_viewer = ll_auth.require_role(["viewer", "analyst", "admin"], secret)
require_analyst = ll_auth.require_role(["analyst", "admin"], secret)


def _incident_exists(db: Session, incident_id: int) -> bool:
    return db.query(Incident).filter(Incident.id == incident_id).first() is not None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ai service starting")
    yield
    logger.info("ai service shutting down")


app = FastAPI(title="LogLens AI Service", lifespan=lifespan)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    rid = ll_logging.new_request_id()
    ll_logging.set_correlation_ids(request_id=rid)
    path = request.url.path
    if path not in ("/health", "/ready", "/metrics"):
        client = request.client.host if request.client else "unknown"
        allowed, retry_after = rate_limiter.allow(client)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(retry_after)},
            )
    start = time.time()
    response = await call_next(request)
    ll_metrics.observe_request(
        SERVICE_NAME, request.method, path, response.status_code, time.time() - start
    )
    return response


@app.get("/health")
def health():
    return ll_health.health_response()


@app.get("/ready")
def ready():
    def db_ok():
        try:
            SessionLocal().execute("SELECT 1")
            return True
        except Exception:
            return False

    return ll_health.readiness_response({"postgres": db_ok})


@app.get("/metrics")
def metrics():
    data, ctype = ll_metrics.metrics_response()
    return Response(content=data, media_type=ctype)


@app.post(
    "/ai/incident/{incident_id}/summarize",
    response_model=schemas.SummaryResponse,
    dependencies=[Depends(require_analyst)],
)
def summarize(
    incident_id: int,
    req: schemas.AIRequest = schemas.AIRequest(),
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm),
):
    if not _incident_exists(db, incident_id):
        raise HTTPException(status_code=404, detail="Incident not found")
    try:
        return investigate.summarize_incident(incident_id, req, llm)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        logger.error(f"LLM client error: {e}")
        raise HTTPException(status_code=502, detail="LLM backend unavailable")


@app.post(
    "/ai/incident/{incident_id}/investigate",
    response_model=schemas.InvestigationResponse,
    dependencies=[Depends(require_analyst)],
)
def investigate_endpoint(
    incident_id: int,
    req: schemas.AIRequest = schemas.AIRequest(),
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm),
):
    if not _incident_exists(db, incident_id):
        raise HTTPException(status_code=404, detail="Incident not found")
    try:
        return investigate.investigate_incident(incident_id, req, llm)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        logger.error(f"LLM client error: {e}")
        raise HTTPException(status_code=502, detail="LLM backend unavailable")


ll_tracing.instrument_app(app, SERVICE_NAME)


if __name__ == "__main__":
    import uvicorn

    time.sleep(10)
    uvicorn.run(app, host="0.0.0.0", port=8000)
