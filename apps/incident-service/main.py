import time
from fastapi import FastAPI
from .database import engine, Base

Base.metadata.create_all(bind=engine)

app = FastAPI(title="LogLens Incident Service")


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    time.sleep(10)
    uvicorn.run(app, host="0.0.0.0", port=8000)
