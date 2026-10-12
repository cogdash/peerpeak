import os

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

import grpc
import classifier_pb2
import classifier_pb2_grpc

app = FastAPI()
GRPC_TARGET = os.environ.get("GRPC_TARGET", "localhost:50051")

BASE_DIR = Path(__file__).resolve().parent

STATIC_DIR = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def read_index():
    return FileResponse(STATIC_DIR / "badges.html")

@app.get("/auth")
async def read_auth():
    return FileResponse(STATIC_DIR / "auth.html")

@app.get("/api/rate-achievement")
async def rate_achievement(text: str = Query(..., min_length=1, max_length=500)):
    # Открываем асинхронный gRPC канал
    async with grpc.aio.insecure_channel(GRPC_TARGET) as channel:
        stub = classifier_pb2_grpc.AchievementClassifierStub(channel)
        
        response = await stub.ClassifyAchievement(
            classifier_pb2.ClassifyRequest(text=text)
        )
        
    return {
        "text": response.text,
        "label": response.label,
        "score": response.score,
        "scores": dict(response.scores)
    }
