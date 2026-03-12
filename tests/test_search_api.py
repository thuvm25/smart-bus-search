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


def test_search_nearby_get():
    """Test GET /api/search/nearby with query parameters."""
    resp = client.get("/api/search/nearby", params={"lat": 10.0, "lon": 106.0})
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["lat"] == 10.0
    assert body["lon"] == 106.0


def test_search_nearby_post():
    """Test POST /api/search/nearby with JSON body."""
    resp = client.post("/api/search/nearby", json={
        "center": {"lat": 10.78, "lon": 106.70},
        "radius_m": 1000,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["radius_m"] == 1000


def test_search_active():
    """Test POST /api/search/active."""
    resp = client.post("/api/search/active", json={"minutes": 0})
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body


def test_search_vehicle_trace():
    """Test POST /api/search/vehicle-trace."""
    resp = client.post("/api/search/vehicle-trace", json={
        "vehicle": "test_vehicle_id",
        "time_window_minutes": 0,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["vehicle"] == "test_vehicle_id"
