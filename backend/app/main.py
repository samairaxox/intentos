import json
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({"level":record.levelname,"message":record.getMessage(),"logger":record.name})

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO,handlers=[handler])
app = FastAPI(title="IntentOS",description="Local-only demo commerce. No real money or multi-user authentication.")
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:3000","http://127.0.0.1:3000"],allow_methods=["GET","POST"],allow_headers=["Content-Type"])
app.include_router(router)

@app.get("/health")
def health() -> dict:
    return {"status":"ok","payment_mode":"mock","catalog":"demo"}
