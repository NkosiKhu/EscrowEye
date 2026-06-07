from fastapi import FastAPI

app = FastAPI(title="EscrowEye API", version="0.1.0")


@app.get("/")
def root():
    return {"app": "EscrowEye", "status": "ok", "version": "0.1.0"}


@app.get("/health")
def health():
    return {"status": "healthy"}
