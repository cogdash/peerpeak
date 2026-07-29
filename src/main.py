from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def read_root():
    return "PeerPeak is ready!"

@app.get("/")
def get_achievements():
    return "Bikepacking"
