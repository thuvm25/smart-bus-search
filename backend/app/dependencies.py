from elasticsearch import Elasticsearch
from .config import settings


def get_es_client():
    # Convert AnyHttpUrl to string for Elasticsearch client
    es_host = str(settings.es_host)
    return Elasticsearch(es_host)