from fastapi import FastAPI
from api.shopping import router as shopping_router
from api.health import router as health_router
import uvicorn
import os

app = FastAPI(title="AvaServer")

app.include_router(shopping_router)
app.include_router(health_router)


@app.get("/")
def home():
    return {
        "status": "online",
        "server": "AvaServer"
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port
    )