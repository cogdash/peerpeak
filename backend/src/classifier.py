"""Thin async wrapper around the achievement classifier gRPC service."""

import os

import grpc

import classifier_pb2
import classifier_pb2_grpc

GRPC_TARGET = os.environ.get("GRPC_TARGET", "localhost:50051")


async def classify(text: str) -> dict:
    """Classify ``text`` and return its label, score and per-label scores.

    ``label`` is either ``"positive"`` (achievement) or ``"negative"``
    (anti-achievement).
    """
    async with grpc.aio.insecure_channel(GRPC_TARGET) as channel:
        stub = classifier_pb2_grpc.AchievementClassifierStub(channel)
        response = await stub.ClassifyAchievement(
            classifier_pb2.ClassifyRequest(text=text)
        )

    return {
        "text": response.text,
        "label": response.label,
        "score": response.score,
        "scores": dict(response.scores),
    }

