from elasticsearch import Elasticsearch
from .config import settings


def get_es_client():
    return Elasticsearch(settings.es_host)