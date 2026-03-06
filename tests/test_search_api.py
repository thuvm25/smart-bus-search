import os
import sys

from fastapi.testclient import TestClient


ROOT = os.path.dirname(os.path.dirname(__file__))
BACKEND_APP_PATH = os.path.join(ROOT, "backend", "app")
sys.path.append(BACKEND_APP_PATH)

from main import app  # noqa: E402


client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_search_nearby_endpoint():
    resp = client.get("/api/search/nearby", params={"lat": 10.0, "lon": 106.0})
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["lat"] == 10.0
    assert body["lon"] == 106.0

