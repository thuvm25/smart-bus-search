from elasticsearch import Elasticsearch

from .config import settings

_es_client: Elasticsearch | None = None


def get_es_client() -> Elasticsearch:
    global _es_client
    if _es_client is None:
        _es_client = Elasticsearch(str(settings.es_host))
    return _es_client


def close_es_client() -> None:
    global _es_client
    if _es_client is not None:
        _es_client.close()
        _es_client = None


def get_index_name() -> str:
    return settings.es_index
