from elasticsearch import Elasticsearch

from ..config import settings


def create_es_client() -> Elasticsearch:
    return Elasticsearch(settings.es_host)

from functools import lru_cache

from elasticsearch import Elasticsearch

from ..config import settings


@lru_cache(maxsize=1)
def get_es_client() -> Elasticsearch:
    """Return a singleton Elasticsearch client instance."""
    return Elasticsearch(settings.es_host)

