"""骨格: すべての口が応答し（落ちない）、中身の無い口は「未実装」を返す。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_index_and_static(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "Pair Agent Manager" in r.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_health(client: TestClient) -> None:
    r = client.get("/api/health").json()
    assert r["implemented"] is True
    assert r["master_root"]


def test_every_api_route_answers_json(client: TestClient) -> None:
    calls = [
        ("get", "/api/dashboard"), ("get", "/api/targets"), ("get", "/api/status"), ("get", "/api/survey"),
        ("get", "/api/checks"), ("get", "/api/situations"), ("get", "/api/fleet"), ("get", "/api/settings"),
    ]
    for method, path in calls:
        r = getattr(client, method)(path)
        assert r.status_code in (200, 400), (path, r.status_code, r.text)
        data = r.json()
        assert "implemented" in data, path
        if data["implemented"] is False:
            assert data["message"] == "未実装"


def test_usecase_entrances_are_implemented(client: TestClient) -> None:
    """docs/usecases.md の口は、すべて中身が入った（未実装を返さない）。"""
    for method, path in (("get", "/api/resident"), ("get", "/api/inbox"), ("get", "/api/activity"), ("get", "/api/managed"),
                         ("get", "/api/sweep"), ("get", "/api/fleet")):
        data = getattr(client, method)(path).json()
        assert data.get("implemented") is True, (path, data)
