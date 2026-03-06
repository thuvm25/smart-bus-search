from fastapi import FastAPI
from .config import settings
from .routers import analytics, search

app = FastAPI(
    title="HCMC Bus GPS Search",
    version="1.0.0"
)

API_PREFIX = settings.api_prefix

# Include routers
app.include_router(
    search.router,
    prefix=f"{API_PREFIX}/search",
    tags=["search"]
)
app.include_router(
    analytics.router,
    prefix=f"{API_PREFIX}/analytics",
    tags=["analytics"]
)

@app.get("/")
async def root():
    return {"message": "HCMC Bus GPS Search API"}