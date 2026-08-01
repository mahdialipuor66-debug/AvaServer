from fastapi import FastAPI
from api.shopping import router

app = FastAPI(title="AvaServer")

app.include_router(router)

@app.get("/")
def home():
    return {
        "status": "online",
        "server": "AvaServer"
    }