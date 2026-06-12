"""DelayBridge backend end-to-end pytest suite.

Covers:
  - Auth (login, /me, invalid creds, cookies)
  - Public demo endpoints (full analysis, flags, variances, correlations,
    dependencies, downstream, onboarding, status, refresh, flag ack/resolve,
    chat admin + dependent, chat suggestions, chat history, alerts)
  - Admin session CRUD + load-demo + public token reachability
  - Bad token 404s
  - MongoDB ObjectId leak check (no _id in responses)
"""
import os
import json
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback to frontend env file
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass

ADMIN_EMAIL = "admin@delaybridge.io"
ADMIN_PASSWORD = "DelayBridge#2026"
DEMO_TOKEN = "demo-nit76-operations"
DEPENDENT_EMAIL = "deepak.verma@nit76.in"


# ---------------- fixtures ----------------
@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def auth(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    return {
        "token": data["access_token"],
        "cookies": r.cookies,
        "user": data["user"],
    }


def _assert_no_objectid(obj):
    """Recursively make sure no Mongo `_id` keys present and value is JSON-friendly."""
    if isinstance(obj, dict):
        assert "_id" not in obj, f"Found leaking _id in response: {list(obj.keys())[:5]}"
        for v in obj.values():
            _assert_no_objectid(v)
    elif isinstance(obj, list):
        for v in obj:
            _assert_no_objectid(v)


# ---------------- AUTH ----------------
class TestAuth:
    def test_login_success_sets_cookies(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body and isinstance(body["access_token"], str)
        assert body["user"]["email"] == ADMIN_EMAIL
        assert body["user"]["role"] == "admin"
        # httpOnly cookies
        cookies = {c.name: c for c in r.cookies}
        assert "access_token" in cookies, "access_token cookie missing"
        assert "refresh_token" in cookies, "refresh_token cookie missing"
        _assert_no_objectid(body)

    def test_login_invalid_credentials(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": ADMIN_EMAIL, "password": "wrong-pass"})
        assert r.status_code == 401

    def test_me_with_bearer(self, api, auth):
        r = api.get(f"{BASE_URL}/api/auth/me",
                    headers={"Authorization": f"Bearer {auth['token']}"})
        assert r.status_code == 200
        body = r.json()
        assert body["email"] == ADMIN_EMAIL
        _assert_no_objectid(body)

    def test_me_unauthenticated(self, api):
        s = requests.Session()
        r = s.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 401


# ---------------- PUBLIC DEMO ----------------
class TestPublicDemo:
    def test_full_analysis(self, api):
        r = api.get(f"{BASE_URL}/api/public/{DEMO_TOKEN}")
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "multi-sheet"
        assert body["totals"]["rows"] == 79, f"expected 79 rows got {body['totals']['rows']}"
        assert "risk_score" in body
        assert isinstance(body.get("flags"), list)
        assert "dependency_chains" in body
        assert "critical_path" in body["dependency_chains"]
        assert body.get("variance") and "summary" in body["variance"]
        _assert_no_objectid(body)

    def test_flags(self, api):
        r = api.get(f"{BASE_URL}/api/public/{DEMO_TOKEN}/flags")
        assert r.status_code == 200
        body = r.json()
        assert "count" in body and "flags" in body
        assert body["count"] == len(body["flags"])
        _assert_no_objectid(body)

    def test_flags_filter_severity_critical(self, api):
        all_r = api.get(f"{BASE_URL}/api/public/{DEMO_TOKEN}/flags").json()
        crit_r = api.get(f"{BASE_URL}/api/public/{DEMO_TOKEN}/flags?severity=Critical").json()
        assert crit_r["count"] <= all_r["count"]
        for f in crit_r["flags"]:
            assert f.get("severity", "").lower() == "critical"

    def test_flags_filter_status_open(self, api):
        r = api.get(f"{BASE_URL}/api/public/{DEMO_TOKEN}/flags?status=Open").json()
        for f in r["flags"]:
            assert f.get("status", "").lower() == "open"

    def test_variances(self, api):
        r = api.get(f"{BASE_URL}/api/public/{DEMO_TOKEN}/variances")
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is True
        assert body["summary"]["compared_sheets"] == 2
        var_rows = body.get("variance_rows") or []
        # ensure sorted desc by max_variance_pct
        if len(var_rows) >= 2:
            mvs = [row.get("max_variance_pct", 0) for row in var_rows]
            assert mvs == sorted(mvs, reverse=True), "variance_rows not sorted desc"

    def test_correlations(self, api):
        r = api.get(f"{BASE_URL}/api/public/{DEMO_TOKEN}/correlations")
        assert r.status_code == 200
        body = r.json()
        for k in ("correlation_matrix", "person_ranking", "department_ranking",
                  "timeline_correlation", "top_delay_reasons"):
            assert k in body, f"missing key {k}"

    def test_dependencies(self, api):
        r = api.get(f"{BASE_URL}/api/public/{DEMO_TOKEN}/dependencies")
        assert r.status_code == 200
        body = r.json()
        assert "critical_path" in body
        # chains / at_risk presence
        assert "chains" in body or "dependency_tree" in body or "at_risk_activities" in body, \
            f"unexpected dependency response keys: {list(body.keys())}"

    def test_downstream(self, api):
        r = api.get(f"{BASE_URL}/api/public/{DEMO_TOKEN}/downstream/{DEPENDENT_EMAIL}")
        assert r.status_code == 200
        body = r.json()
        assert "activities" in body or "blocked" in body, f"keys={list(body.keys())}"
        blocked = body.get("blocked", [])
        if blocked:
            sample = blocked[0]
            for k in ("blocking_activity", "blocker_person", "reason"):
                assert k in sample, f"missing {k} in blocked entry"

    def test_onboarding(self, api):
        r = api.get(f"{BASE_URL}/api/public/{DEMO_TOKEN}/onboarding")
        assert r.status_code == 200
        body = r.json()
        assert len(body["steps"]) == 7
        assert "apps_script_code" in body and "doGet" in body["apps_script_code"]

    def test_status(self, api):
        r = api.get(f"{BASE_URL}/api/public/{DEMO_TOKEN}/status")
        assert r.status_code == 200
        body = r.json()
        labels = sorted([s["label"] for s in body["sheets"]])
        assert labels == ["A", "B"]
        assert all(s["connected"] for s in body["sheets"])

    def test_refresh_demo_no_op(self, api):
        r = api.post(f"{BASE_URL}/api/public/{DEMO_TOKEN}/refresh")
        assert r.status_code == 200
        body = r.json()
        assert body.get("is_demo") is True


class TestFlagActions:
    def test_acknowledge_then_resolve(self, api):
        flags = api.get(f"{BASE_URL}/api/public/{DEMO_TOKEN}/flags").json()["flags"]
        assert flags, "no flags to act on"
        # Find an Open flag if possible
        flag = next((f for f in flags if f.get("status", "").lower() == "open"), flags[0])
        fid = flag.get("id") or flag.get("uid")
        ack = api.post(f"{BASE_URL}/api/public/{DEMO_TOKEN}/flag/{fid}/acknowledge", json={"note": "ack-test"})
        assert ack.status_code == 200, ack.text
        assert ack.json()["status"] == "Acknowledged"
        res = api.post(f"{BASE_URL}/api/public/{DEMO_TOKEN}/flag/{fid}/resolve", json={"note": "res-test"})
        assert res.status_code == 200
        assert res.json()["status"] == "Resolved"


class TestChat:
    def test_admin_chat_real_names(self, api):
        r = api.post(f"{BASE_URL}/api/public/{DEMO_TOKEN}/chat",
                     json={"message": "Give me a short summary of the top delayed activity and who is responsible."})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["mode"] == "admin"
        reply = body["reply"]
        assert isinstance(reply, str) and len(reply) > 20
        # Should reference a real name or activity from demo data
        markers = ["Rahul", "Deepak", "Priya", "Vendor", "Budget", "NIT", "Invoice", "Approval"]
        assert any(m.lower() in reply.lower() for m in markers), f"reply lacks real-data anchors: {reply[:300]}"

    def test_dependent_chat_pressure_loop(self, api):
        # baseline alerts count
        before = api.get(f"{BASE_URL}/api/public/{DEMO_TOKEN}/alerts").json()["count"]
        r = api.post(f"{BASE_URL}/api/public/{DEMO_TOKEN}/chat",
                     json={"message": "Who is blocking me right now?", "email": DEPENDENT_EMAIL})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["mode"] == "dependent"
        reply = body["reply"].lower()
        assert "deepak" in reply or "you" in reply, f"reply not personally addressed: {body['reply'][:200]}"
        autos = body.get("auto_actions", [])
        if autos:
            assert all(a.get("type") == "dependent_pressure_loop" for a in autos)
            assert all("MOCKED" in (a.get("status") or "") for a in autos)
            # alerts collection should have grown
            after = api.get(f"{BASE_URL}/api/public/{DEMO_TOKEN}/alerts").json()["count"]
            assert after >= before + len(autos)

    def test_chat_suggestions_admin(self, api):
        r = api.get(f"{BASE_URL}/api/public/{DEMO_TOKEN}/chat/suggestions")
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "admin"
        assert isinstance(body["suggestions"], list) and body["suggestions"]

    def test_chat_suggestions_dependent(self, api):
        r = api.get(f"{BASE_URL}/api/public/{DEMO_TOKEN}/chat/suggestions",
                    params={"email": DEPENDENT_EMAIL})
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "dependent"
        assert isinstance(body["suggestions"], list) and body["suggestions"]

    def test_chat_history(self, api):
        r = api.get(f"{BASE_URL}/api/public/{DEMO_TOKEN}/chat/history")
        assert r.status_code == 200
        body = r.json()
        assert "history" in body and isinstance(body["history"], list)
        # we already chatted twice above
        assert body["count"] >= 1
        _assert_no_objectid(body)

    def test_alerts(self, api):
        r = api.get(f"{BASE_URL}/api/public/{DEMO_TOKEN}/alerts")
        assert r.status_code == 200
        body = r.json()
        assert "alerts" in body
        _assert_no_objectid(body)


# ---------------- ADMIN SESSIONS ----------------
class TestAdminSessions:
    created_id = None
    created_token = None

    def _hdr(self, auth):
        return {"Authorization": f"Bearer {auth['token']}"}

    def test_create_session(self, api, auth):
        r = api.post(f"{BASE_URL}/api/sessions",
                     headers=self._hdr(auth),
                     json={"name": "TEST_pytest_session"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "id" in body and "public_token" in body
        TestAdminSessions.created_id = body["id"]
        TestAdminSessions.created_token = body["public_token"]
        _assert_no_objectid(body)

    def test_list_sessions(self, api, auth):
        r = api.get(f"{BASE_URL}/api/sessions", headers=self._hdr(auth))
        assert r.status_code == 200
        items = r.json()
        assert any(s["id"] == TestAdminSessions.created_id for s in items)

    def test_get_session(self, api, auth):
        r = api.get(f"{BASE_URL}/api/sessions/{TestAdminSessions.created_id}",
                    headers=self._hdr(auth))
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == TestAdminSessions.created_id
        assert body["public_token"] == TestAdminSessions.created_token

    def test_load_demo_runs_analysis(self, api, auth):
        r = api.post(f"{BASE_URL}/api/sessions/{TestAdminSessions.created_id}/load-demo",
                     headers=self._hdr(auth))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("mode") == "multi-sheet"
        assert "risk_score" in body
        assert "flags_count" in body

    def test_public_reachable_after_load_demo(self, api):
        r = api.get(f"{BASE_URL}/api/public/{TestAdminSessions.created_token}")
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "multi-sheet"

    def test_invalid_sheet_url(self, api, auth):
        r = api.post(f"{BASE_URL}/api/sessions/{TestAdminSessions.created_id}/sheets",
                     headers=self._hdr(auth),
                     json={"url": "not-a-url", "label": "C"})
        assert r.status_code == 400
        msg = (r.json().get("detail") or "").lower()
        assert "http" in msg or "json" in msg or "url" in msg, f"unexpected msg: {msg}"

    def test_delete_session_and_404_after(self, api, auth):
        d = api.delete(f"{BASE_URL}/api/sessions/{TestAdminSessions.created_id}",
                       headers=self._hdr(auth))
        assert d.status_code == 200
        g = api.get(f"{BASE_URL}/api/sessions/{TestAdminSessions.created_id}",
                    headers=self._hdr(auth))
        assert g.status_code == 404


# ---------------- BAD TOKEN ----------------
class TestBadToken:
    @pytest.mark.parametrize("path", [
        "", "/flags", "/variances", "/correlations", "/dependencies",
        "/onboarding", "/status", "/alerts", "/chat/history",
    ])
    def test_bad_token_404(self, api, path):
        r = api.get(f"{BASE_URL}/api/public/totally-bogus-token-xyz{path}")
        # onboarding doesn't read DB; everything else should 404 for unknown token.
        # If onboarding returns 200, that's acceptable - it's a public help endpoint.
        if path == "/onboarding":
            assert r.status_code in (200, 404)
        else:
            assert r.status_code == 404, f"path={path} got {r.status_code}"


# ---------------- ObjectId leak ----------------
class TestObjectIdLeak:
    @pytest.mark.parametrize("path", [
        f"/api/public/{DEMO_TOKEN}",
        f"/api/public/{DEMO_TOKEN}/flags",
        f"/api/public/{DEMO_TOKEN}/variances",
        f"/api/public/{DEMO_TOKEN}/correlations",
        f"/api/public/{DEMO_TOKEN}/chat/history",
        f"/api/public/{DEMO_TOKEN}/alerts",
    ])
    def test_no_mongo_id(self, api, path):
        r = api.get(f"{BASE_URL}{path}")
        assert r.status_code == 200, f"{path}: {r.status_code}"
        _assert_no_objectid(r.json())
