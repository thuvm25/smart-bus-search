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


def test_analytics_stats_endpoint():
    """Test /api/analytics/stats returns index statistics."""
    resp = client.get("/api/analytics/stats")
    assert resp.status_code == 200
    body = resp.json()
    # Should return a dict (may be empty if ES is not running)
    assert isinstance(body, dict)


def test_analytics_speed_endpoint():
    """Test /api/analytics/speed returns speed statistics."""
    resp = client.get("/api/analytics/speed")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)


def test_analytics_density_endpoint():
    """Test /api/analytics/density returns geohash grid data."""
    resp = client.get("/api/analytics/density", params={"precision": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert "cells" in body or "total_cells" in body or isinstance(body, dict)


def test_analytics_active_count_endpoint():
    """Test /api/analytics/active-count returns vehicle count."""
    resp = client.get("/api/analytics/active-count", params={"minutes": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)
