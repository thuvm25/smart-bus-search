from fastapi import FastAPI
from .config import settings

app = FastAPI(
    title="HCMC Bus GPS Search",
    version="1.0.0"
)

API_PREFIX = settings.api_prefix