import warnings
import asyncio
import grpc
from concurrent import futures
from transformers import pipeline

import classifier_pb2
import classifier_pb2_grpc

warnings.filterwarnings("ignore", category=FutureWarning)

CANDIDATE_LABELS = ["успех", "провал"]
POSITIVE_LABEL = "успех"

class ClassifierServicer(classifier_pb2_grpc.AchievementClassifierServicer):
    def __init__(self):
        print("Loading model...")
        self._classifier = pipeline(
                "zero-shot-classification",
                model="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
                )
        print("Model loaded successfully!")

    async def ClassifyAchievement(self, request, context):
        text = request.text
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(
                None, 
                lambda: self._classifier(
                    text,
                    candidate_labels=CANDIDATE_LABELS,
                    hypothesis_template="Это {}.",
                    multi_label=False
                    )
                )

        top = res["labels"][0]
        label = "positive" if top == POSITIVE_LABEL else "negative"
        score = round(res["scores"][0], 3)
        scores = {lbl: round(s, 3) for lbl, s in zip(res["labels"], res["scores"])}

        return classifier_pb2.ClassifyResponse(
                text=text,
                label=label,
                score=score,
                scores=scores
                )

async def serve():
    server = grpc.aio.server()
    classifier_pb2_grpc.add_AchievementClassifierServicer_to_server(
        ClassifierServicer(), server
    )
    server.add_insecure_port('[::]:50051')
    print("gRPC Server started on port 50051")
    await server.start()
    await server.wait_for_termination()

if __name__ == '__main__':
    asyncio.run(serve())
