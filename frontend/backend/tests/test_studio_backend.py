"""Studio (Dependency Mapping) backend tests."""
import os
import uuid
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "admin@delaybridge.io"
ADMIN_PASSWORD = "DelayBridge#2026"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def auth(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}",
                      "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def created_maps():
    return []


# ---------- AUTH REQUIRED ----------
class TestStudioAuth:
    def test_create_map_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/studio/maps",
                          json={"title": "noauth"}, timeout=15)
        assert r.status_code in (401, 403)

    def test_list_maps_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/studio/maps", timeout=15)
        assert r.status_code in (401, 403)


# ---------- CRUD ----------
class TestStudioMapCRUD:
    def test_create_map(self, auth, created_maps):
        r = auth.post(f"{BASE_URL}/api/studio/maps",
                      json={"title": "TEST_studio_map"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert "id" in d and "share_token" in d
        assert d["share_mode"] == "private"
        assert d["title"] == "TEST_studio_map"
        created_maps.append(d["id"])

    def test_list_maps(self, auth, created_maps):
        r = auth.get(f"{BASE_URL}/api/studio/maps")
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        ids = [m["id"] for m in items]
        assert created_maps[0] in ids
        first = next(m for m in items if m["id"] == created_maps[0])
        assert "nodes_count" in first and "edges_count" in first

    def test_save_and_get_map(self, auth, created_maps):
        mid = created_maps[0]
        nodes = [
            {"id": "n1", "type": "custom", "position": {"x": 0, "y": 0},
             "data": {"name": "UI", "category": "Frontend"}},
            {"id": "n2", "type": "custom", "position": {"x": 200, "y": 0},
             "data": {"name": "Postgres", "category": "Database"}},
        ]
        edges = [{"id": "e1", "source": "n1", "target": "n2",
                  "type": "dependency", "data": {"type": "data"}}]
        r = auth.put(f"{BASE_URL}/api/studio/maps/{mid}",
                     json={"title": "TEST_studio_updated", "nodes": nodes, "edges": edges})
        assert r.status_code == 200, r.text
        assert r.json()["nodes"] == 2 and r.json()["edges"] == 1

        g = auth.get(f"{BASE_URL}/api/studio/maps/{mid}")
        assert g.status_code == 200
        d = g.json()
        assert d["title"] == "TEST_studio_updated"
        assert len(d["nodes"]) == 2 and len(d["edges"]) == 1


# ---------- ANALYZE ----------
class TestStudioAnalyze:
    def test_analyze_frontend_to_database_bad_pattern(self, auth, created_maps):
        mid = created_maps[0]
        # current saved graph is Frontend->Database from previous test
        r = auth.post(f"{BASE_URL}/api/studio/maps/{mid}/analyze")
        assert r.status_code == 200
        d = r.json()
        assert d["nodes"] == 2 and d["edges"] == 1
        texts = " ".join(i.get("text", "") for i in d.get("insights", []))
        assert "Frontend/UI directly accessing Database" in texts or any(
            bp.get("issue") == "Frontend/UI directly accessing Database"
            for bp in d.get("bad_patterns", [])
        )

    def test_analyze_cycle_detection(self, auth):
        r = auth.post(f"{BASE_URL}/api/studio/maps", json={"title": "TEST_cycle"})
        mid = r.json()["id"]
        nodes = [
            {"id": "A", "type": "custom", "position": {"x": 0, "y": 0},
             "data": {"name": "A", "category": "Service"}},
            {"id": "B", "type": "custom", "position": {"x": 100, "y": 0},
             "data": {"name": "B", "category": "Service"}},
            {"id": "C", "type": "custom", "position": {"x": 200, "y": 0},
             "data": {"name": "C", "category": "Service"}},
        ]
        edges = [
            {"id": "eAB", "source": "A", "target": "B"},
            {"id": "eBC", "source": "B", "target": "C"},
            {"id": "eCA", "source": "C", "target": "A"},
        ]
        auth.put(f"{BASE_URL}/api/studio/maps/{mid}",
                 json={"nodes": nodes, "edges": edges})
        a = auth.post(f"{BASE_URL}/api/studio/maps/{mid}/analyze")
        assert a.status_code == 200
        d = a.json()
        assert len(d["cycles"]) >= 1
        assert d["is_dag"] is False
        assert d["scores"]["health"] < 100
        # cleanup
        auth.delete(f"{BASE_URL}/api/studio/maps/{mid}")

    def test_analyze_orphan_detection(self, auth):
        r = auth.post(f"{BASE_URL}/api/studio/maps", json={"title": "TEST_orphan"})
        mid = r.json()["id"]
        nodes = [
            {"id": "x1", "type": "custom", "position": {"x": 0, "y": 0},
             "data": {"name": "Lonely", "category": "Service"}}
        ]
        auth.put(f"{BASE_URL}/api/studio/maps/{mid}",
                 json={"nodes": nodes, "edges": []})
        a = auth.post(f"{BASE_URL}/api/studio/maps/{mid}/analyze")
        d = a.json()
        assert "x1" in d["orphans"]
        texts = " ".join(i.get("text", "").lower() for i in d.get("insights", []))
        assert "orphan" in texts
        auth.delete(f"{BASE_URL}/api/studio/maps/{mid}")


# ---------- SHARE / PUBLIC ----------
class TestStudioShare:
    def test_public_private_returns_403(self, auth, created_maps):
        mid = created_maps[0]
        m = auth.get(f"{BASE_URL}/api/studio/maps/{mid}").json()
        tok = m["share_token"]
        # ensure private
        auth.post(f"{BASE_URL}/api/studio/maps/{mid}/share", json={"mode": "private"})
        r = requests.get(f"{BASE_URL}/api/studio/public/{tok}", timeout=15)
        assert r.status_code == 403

    def test_public_mode_returns_data(self, auth, created_maps):
        mid = created_maps[0]
        s = auth.post(f"{BASE_URL}/api/studio/maps/{mid}/share",
                      json={"mode": "public"})
        assert s.status_code == 200
        body = s.json()
        assert body["share_mode"] == "public"
        tok = body["share_token"]
        r = requests.get(f"{BASE_URL}/api/studio/public/{tok}", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "nodes" in d and "edges" in d
        assert d["share_mode"] == "public"

    def test_public_readonly_put_403(self, auth, created_maps):
        mid = created_maps[0]
        s = auth.post(f"{BASE_URL}/api/studio/maps/{mid}/share",
                      json={"mode": "readonly"})
        tok = s.json()["share_token"]
        r = requests.put(f"{BASE_URL}/api/studio/public/{tok}",
                         json={"title": "hack"}, timeout=15)
        assert r.status_code == 403

    def test_public_editable_put_succeeds(self, auth, created_maps):
        mid = created_maps[0]
        s = auth.post(f"{BASE_URL}/api/studio/maps/{mid}/share",
                      json={"mode": "editable"})
        tok = s.json()["share_token"]
        new_title = "TEST_editable_" + uuid.uuid4().hex[:6]
        r = requests.put(f"{BASE_URL}/api/studio/public/{tok}",
                         json={"title": new_title}, timeout=15)
        assert r.status_code == 200
        # verify persistence via owner GET
        g = auth.get(f"{BASE_URL}/api/studio/maps/{mid}").json()
        assert g["title"] == new_title


# ---------- FETCH ----------
class TestStudioFetch:
    def test_fetch_invalid_url(self, auth):
        r = auth.post(f"{BASE_URL}/api/studio/fetch",
                      json={"url": "https://example.com/not-apps-script"})
        assert r.status_code == 400
        assert "detail" in r.json()


# ---------- DELETE ----------
class TestStudioDelete:
    def test_delete_map(self, auth, created_maps):
        mid = created_maps[0]
        r = auth.delete(f"{BASE_URL}/api/studio/maps/{mid}")
        assert r.status_code == 200
        g = auth.get(f"{BASE_URL}/api/studio/maps/{mid}")
        assert g.status_code == 404


# ---------- REGRESSION ----------
class TestRegression:
    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=15)
        assert r.status_code == 200

    def test_auth_me(self, auth):
        r = auth.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL
