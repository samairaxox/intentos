import json
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError,DBAPIError
from app.api.routes import router
from app.api.commerce_routes import router as commerce_router
from app.api.multi_routes import router as multi_router

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({"level":record.levelname,"message":record.getMessage(),"logger":record.name})

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO,handlers=[handler])
app = FastAPI(title="IntentOS",description="Local-only demo commerce. No real money or multi-user authentication.")
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:3000","http://127.0.0.1:3000"],allow_methods=["GET","POST"],allow_headers=["Content-Type","Authorization"])
app.include_router(router)
app.include_router(commerce_router)
app.include_router(multi_router)
from app.api.finance_routes import router as finance_router
app.include_router(finance_router)
from app.core.auth import authentication
app.middleware("http")(authentication)

@app.exception_handler(DBAPIError)
async def database_error(request,exc):
    unavailable=isinstance(exc,OperationalError) or exc.connection_invalidated
    logging.getLogger(__name__).error('database_request_failed: %s',type(exc).__name__)
    return JSONResponse(status_code=503 if unavailable else 500,content={'detail':{
        'code':'DATABASE_UNAVAILABLE' if unavailable else 'DATABASE_ERROR',
        'message':'Database temporarily unavailable. Inspect transaction state before retrying financial writes.' if unavailable else 'Database operation failed.'}})

@app.get("/health")
def health() -> dict:
    return {"status":"ok","payment_mode":"mock","catalog":"demo"}
