from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import os
from datetime import datetime
from . import crud, models, schemas, database
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="LogLens API")

# Dependency
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Global embedding model and Qdrant client (initialized once)
EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "log_collection")
qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

@app.post("/logs/", response_model=schemas.LogEntryRead)
def create_log(log: schemas.LogEntryCreate, db: Session = Depends(get_db)):
    return crud.create_log_entry(db=db, log=log)

@app.get("/logs/", response_model=List[schemas.LogEntryRead])
def read_logs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_logs(db, skip=skip, limit=limit)

@app.get("/search/", response_model=List[schemas.LogEntryRead])
def semantic_search(q: str = Query(..., description="Natural language search query"), limit: int = Query(10, ge=1, le=100)):
    # Encode query
    vector = EMBEDDING_MODEL.encode(q).tolist()
    # Search in Qdrant
    search_result = qdrant_client.search(
        collection_name=COLLECTION_NAME,
        query_vector=vector,
        limit=limit
    )
    results = []
    for point in search_result:
        payload = point.payload.copy()
        # Ensure we have required fields; if missing, provide defaults
        payload.setdefault('id', 0)  # fallback id
        # timestamp may be string; convert to datetime if needed
        ts = payload.get('timestamp')
        if isinstance(ts, str):
            try:
                payload['timestamp'] = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            except:
                payload['timestamp'] = datetime.utcnow()
        elif not isinstance(ts, datetime):
            payload['timestamp'] = datetime.utcnow()
        results.append(payload)
    return results
