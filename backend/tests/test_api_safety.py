from fastapi.testclient import TestClient

from backend import server


def test_generate_rejects_invalid_land_count_before_backend_access():
    with TestClient(server.app) as client:
        response = client.post("/api/generate", json={"commander": "Krenko, Mob Boss", "land_count": 100})

    assert response.status_code == 422
    assert "less than or equal to 50" in response.text


def test_default_cors_allows_only_the_deployed_frontend():
    with TestClient(server.app) as client:
        allowed = client.get("/api/", headers={"Origin": "https://xaric24.github.io"})
        rejected = client.get("/api/", headers={"Origin": "https://untrusted.example"})

    assert allowed.headers["access-control-allow-origin"] == "https://xaric24.github.io"
    assert "access-control-allow-origin" not in rejected.headers


def test_finished_jobs_expire():
    server.JOBS.clear()
    server.JOBS["expired"] = {"status": "done", "completed_at": 10.0}

    server._prune_jobs(now=10.0 + server.JOB_TTL_SECONDS)

    assert "expired" not in server.JOBS


def test_generation_rate_limit_rejects_excess_requests(monkeypatch):
    server.REQUEST_LOG.clear()
    monkeypatch.setattr(server, "RATE_LIMIT_MAX_REQUESTS", 2)

    assert server._allow_generate_request("test-client", now=1.0)
    assert server._allow_generate_request("test-client", now=2.0)
    assert not server._allow_generate_request("test-client", now=3.0)
