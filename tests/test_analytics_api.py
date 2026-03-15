import os
import sys

from fastapi.testclient import TestClient

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.main import app  # noqa: E402

client = TestClient(app)


def test_analytics_stats_endpoint():
    resp = client.get("/api/analytics/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)


def test_analytics_density_endpoint():
    resp = client.get("/api/analytics/density")
    assert resp.status_code == 200
    body = resp.json()
    assert "cells" in body
    assert "total_cells" in body


def test_analytics_speed_endpoint():
    resp = client.get("/api/analytics/speed")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)
