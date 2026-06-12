"""Tests for new Phase 1B export endpoints:
- GET /api/public/{token}/export (with/without fields)
- GET/POST /api/sessions/{sid}/export-config (admin auth)
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_EMAIL = "admin@delaybridge.io"
ADMIN_PASSWORD = "DelayBridge#2026"
DEMO_TOKEN = "demo-nit76-operations"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def auth(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ---------- /export public endpoint ----------
class TestPublicExport:
    def test_export_no_fields_returns_full(self, api):
        r = api.get(f"{BASE_URL}/api/public/{DEMO_TOKEN}/export")
        assert r.status_code == 200, r.text
        body = r.json()
        # Full analysis fields present
        for k in ("mode", "totals", "risk_score", "flags", "variance"):
            assert k in body, f"missing key {k} in full export"
        assert body["mode"] == "multi-sheet"
        # No mongo _id leak
        assert "_id" not in body

    def test_export_with_specific_fields(self, api):
        url = f"{BASE_URL}/api/public/{DEMO_TOKEN}/export?fields=totals,risk_score,flags"
        r = api.get(url)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "totals" in body
        assert "risk_score" in body
        assert "flags" in body
        # echo
        assert set(body.get("_fields_returned", [])) == {"totals", "risk_score", "flags"}
        assert body.get("_fields_unknown") == []
        # confirm only requested fields + meta
        assert "variance" not in body
        assert "dependency_chains" not in body

    def test_export_unknown_field(self, api):
        url = f"{BASE_URL}/api/public/{DEMO_TOKEN}/export?fields=totals,bogus_field"
        r = api.get(url)
        assert r.status_code == 200
        body = r.json()
        assert "totals" in body
        assert body["_fields_unknown"] == ["bogus_field"]
        assert body["_fields_returned"] == ["totals"]

    def test_export_bad_token_404(self, api):
        r = api.get(f"{BASE_URL}/api/public/bogus-xyz-token/export")
        assert r.status_code == 404


# ---------- /export-config admin endpoint ----------
class TestExportConfig:
    session_id = None

    def _hdr(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_create_session_for_config(self, api, auth):
        r = api.post(f"{BASE_URL}/api/sessions",
                     headers=self._hdr(auth),
                     json={"name": "TEST_export_config"})
        assert r.status_code == 200
        TestExportConfig.session_id = r.json()["id"]

    def test_get_config_unauth(self, api):
        r = requests.get(f"{BASE_URL}/api/sessions/{TestExportConfig.session_id}/export-config")
        assert r.status_code == 401

    def test_get_config_default_empty(self, api, auth):
        r = api.get(f"{BASE_URL}/api/sessions/{TestExportConfig.session_id}/export-config",
                    headers=self._hdr(auth))
        assert r.status_code == 200
        assert r.json() == {"fields": []}

    def test_post_config_persists(self, api, auth):
        payload = {"fields": ["totals", "flags"]}
        r = api.post(f"{BASE_URL}/api/sessions/{TestExportConfig.session_id}/export-config",
                     headers=self._hdr(auth), json=payload)
        assert r.status_code == 200
        assert r.json()["fields"] == ["totals", "flags"]

        # Verify GET reflects saved fields
        g = api.get(f"{BASE_URL}/api/sessions/{TestExportConfig.session_id}/export-config",
                    headers=self._hdr(auth))
        assert g.status_code == 200
        assert g.json()["fields"] == ["totals", "flags"]

    def test_cleanup(self, api, auth):
        if TestExportConfig.session_id:
            api.delete(f"{BASE_URL}/api/sessions/{TestExportConfig.session_id}",
                       headers=self._hdr(auth))
