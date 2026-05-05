"""
Elasticsearch client singleton.
Reads ES_HOST and ES_INDEX from environment variables.
"""

from __future__ import annotations

import os
from typing import Optional
from elasticsearch import Elasticsearch
from dotenv import load_dotenv

load_dotenv()

ES_HOST  = os.getenv("ES_HOST", "http://localhost:9200")
ES_INDEX = os.getenv("ES_INDEX", "bus_waypoints")

_client: Optional[Elasticsearch] = None


def get_es() -> Elasticsearch:
    """Return a cached Elasticsearch client instance."""
    global _client
    if _client is None:
        _client = Elasticsearch(ES_HOST)
    return _client


def get_index() -> str:
    return ES_INDEX
