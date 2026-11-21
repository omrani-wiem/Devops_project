import pytest
from fastapi.testclient import TestClient
from app import app, tasks


@pytest.fixture
def client():
    tasks.clear()
    return TestClient(app)



def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_create_and_get_task(client):
    r = client.post("/tasks", json={"title": "learn devops"})
    assert r.status_code == 201
    assert client.get(f"/tasks/{r.json()['id']}").json()["title"] == "learn devops"

def test_create_task_without_title(client):
    assert client.post("/tasks", json={}).status_code == 422


def test_task_not_found(client):
    assert client.get("/tasks/999").status_code == 404


def test_metrics_exposed(client):
    client.get("/health")
    assert b"http_requests_total" in client.get("/metrics").content