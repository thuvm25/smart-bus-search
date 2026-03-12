"""ES client helper — kept for backward compatibility.

Primary client creation is in dependencies.py.
"""

from elasticsearch import Elasticsearch

from ..config import settings


def create_es_client() -> Elasticsearch:
    return Elasticsearch(str(settings.es_host))
