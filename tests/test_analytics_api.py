import os
import sys

from fastapi.testclient import TestClient


ROOT = os.path.dirname(os.path.dirname(__file__))
BACKEND_APP_PATH = os.path.join(ROOT, "backend", "app")
sys.path.append(BACKEND_APP_PATH)

from main import app  # noqa: E402


client = TestClient(app)


def test_analytics_summary_endpoint():
    resp = client.get("/api/analytics/summary")
    assert resp.status_code == 200
    assert "message" in resp.json()

