"""骨格: すべての口が応答し、中身の無い口は「未実装」を返す（落ちない）。"""

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


def test_every_api_route_answers(client: TestClient) -> None:
    """どの口も 200 で JSON を返す。未実装なら message が「未実装」。"""
    calls = [
        ("get", "/api/dashboard", None), ("get", "/api/targets", None),
        ("post", "/api/targets/discover", {}), ("get", "/api/status", None),
        ("get", "/api/survey", None), ("get", "/api/checks", None),
        ("get", "/api/situations", None), ("get", "/api/fleet", None),
        ("get", "/api/settings", None),
    ]
    for method, path, body in calls:
        r = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
        assert r.status_code == 200, (path, r.status_code, r.text)
        data = r.json()
        assert "implemented" in data, path
        if data["implemented"] is False:
            assert data["message"] == "未実装"
