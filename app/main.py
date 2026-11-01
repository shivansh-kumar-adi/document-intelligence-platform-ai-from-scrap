import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api import router
from app.config import get_settings
from app.database import Base, engine


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings = get_settings()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    yield

app = FastAPI(title=settings.app_name, version="1.0.0", docs_url="/docs", redoc_url="/redoc", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://localhost:3000"],
                   allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix=settings.api_prefix)


@app.exception_handler(Exception)
async def unhandled(_request: Request, exc: Exception):
    logging.getLogger("api").exception("Unhandled request failure: %s", type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/")
def root():
    return {"name": settings.app_name, "docs": "/docs", "health": f"{settings.api_prefix}/health"}

