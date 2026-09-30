from fastapi import FastAPI

app = FastAPI(title="Advocondo API")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
