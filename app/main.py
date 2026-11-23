from fastapi import FastAPI

from app import db

app = FastAPI(title="Funds")


@app.get("/funds")
def list_funds():
    return db.list_funds()
