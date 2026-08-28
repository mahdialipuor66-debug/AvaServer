from fastapi import FastAPI
from api.shopping import router as shopping_router
from api.health import router as health_router

app = FastAPI(title="AvaServer")

app.include_router(shopping_router)
app.include_router(health_router)


@app.get("/")
def home():
    return {
        "status": "online",
        "server": "AvaServer"
    }