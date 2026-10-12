import warnings
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from transformers import pipeline

warnings.filterwarnings("ignore", category=FutureWarning)

# метки не должны пересекаться по токенам — иначе NLI путается
CANDIDATE_LABELS = ["успех", "провал"]
POSITIVE_LABEL = "успех"

_classifier = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # грузим модель один раз при старте
    global _classifier
    _classifier = pipeline(
        "zero-shot-classification",
        model="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
    )
    yield
    _classifier = None


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # для локальной разработки ок
    allow_methods=["*"],
    allow_headers=["*"],
)

def _classify(text: str) -> dict:
    res = _classifier(
        text,
        candidate_labels=CANDIDATE_LABELS,
        hypothesis_template="Это {}.",
        multi_label=False,
    )
    top = res["labels"][0]
    return {
        "label": "positive" if top == POSITIVE_LABEL else "negative",
        "score": round(res["scores"][0], 3),
        "scores": {
            lbl: round(s, 3) for lbl, s in zip(res["labels"], res["scores"])
        },
    }


@app.get("/rate")
async def rate(text: str = Query(..., min_length=1, max_length=500)):
    # pipeline синхронный → уводим в threadpool, чтобы не блокировать loop
    result = await run_in_threadpool(_classify, text)
    return {"text": text, **result}


@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": _classifier is not None}
