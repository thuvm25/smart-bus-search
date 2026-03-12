from elasticsearch import Elasticsearch

from .config import settings


def get_es_client() -> Elasticsearch:
    return Elasticsearch(str(settings.es_host))


def get_index_name() -> str:
    return settings.es_index
