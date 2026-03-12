from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from .config import settings
from .dependencies import get_es_client
from .models.mapping import BUS_WAYPOINT_MAPPING
from .routers import analytics, benchmark, ingest, search


@asynccontextmanager
async def lifespan(app: FastAPI):
    es = get_es_client()
    if not es.indices.exists(index=settings.es_index):
        es.indices.create(index=settings.es_index, **BUS_WAYPOINT_MAPPING)
        print(f"Created index '{settings.es_index}'")
    es.close()
    yield


app = FastAPI(title="Smart Bus GPS Search API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(ingest.router, prefix="/api/ingest", tags=["ingest"])
app.include_router(benchmark.router, prefix="/api/benchmark", tags=["benchmark"])
