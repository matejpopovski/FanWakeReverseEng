"""API, auth, webhook, OAuth, live-client contract and migration tests."""

from __future__ import annotations

import json
import time
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.fanvue import oauth
from app.fanvue.base import NeedsReconnect, NotContactable
from app.fanvue.live import LiveFanvueClient
from app.fanvue.webhooks import sign, verify_signature
from app.models import Fan, FanvueConnection, Job, PpvTemplate, WebhookEvent


# ------------------------------------------------------------------------------------------------ auth
def test_auth_and_csrf(seeded: Session) -> None:
    from app.main import create_app

    with TestClient(create_app()) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/fans").status_code == 401
        assert c.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
        assert c.post("/api/auth/login", json={"password": "test-password"}).status_code == 200
        assert c.get("/api/fans").status_code == 200
        assert c.patch("/api/fans/1", json={"notes": "x"}).status_code == 403  # no CSRF header
        assert c.patch("/api/fans/1", json={"notes": "x"},
                       headers={"X-Requested-With": "wakeful"}).status_code == 200


# ------------------------------------------------------------------------------------------------ core API
def test_dashboard_status_and_fans(client: TestClient) -> None:
    s = client.get("/api/status").json()
    assert s["mode"] == "mock" and s["live_sending_enabled"] is False and s["autopilot_mode"] == "review"
    d = client.get("/api/dashboard?days=30").json()
    assert d["kpis"]["total_fans"] == 12 and "series" in d and "ai_usage" in d
    fans = client.get("/api/fans?segment=all&limit=5").json()
    assert fans["total"] == 12 and len(fans["items"]) == 5
    assert client.get("/api/fans?segment=bogus").status_code == 400
    q = fans["items"][0]["display_name"].split()[0]
    assert any(q in f["display_name"] for f in client.get(f"/api/fans?q={q}").json()["items"])
    fid = fans["items"][0]["id"]
    detail = client.get(f"/api/fans/{fid}").json()
    assert "metrics" in detail and "content" in detail and len(detail["metrics"]) == 16
    r = client.patch(f"/api/fans/{fid}", json={"tags": ["vip", " vip ", ""], "review_mode": "manual",
                                               "memory": "[ABOUT]\nlikes hiking"})
    assert r.json()["tags"] == ["vip"] and r.json()["review_mode"] == "manual"
    assert client.patch(f"/api/fans/{fid}", json={"review_mode": "bad"}).status_code == 422
    assert client.patch(f"/api/fans/{fid}", json={"memory": "x" * 3001}).status_code == 422


def test_conversations_compose_and_generate(client: TestClient, seeded: Session) -> None:
    conv = client.get("/api/conversations").json()["items"]
    assert conv
    fan = seeded.scalar(select(Fan).where(Fan.status != "not_contactable"))
    msgs = client.get(f"/api/conversations/{fan.id}/messages").json()
    assert "items" in msgs
    g = client.post(f"/api/fans/{fan.id}/generate", json={"kind": "reply"})
    assert g.status_code == 200 and g.json()["status"] == "pending"
    c = client.post(f"/api/fans/{fan.id}/compose", json={"text": "hand written"})
    assert c.status_code == 200 and c.json()["status"] == "approved"
    assert client.post(f"/api/fans/{fan.id}/compose", json={"text": ""}).status_code == 422
    # composing supersedes the pending AI suggestion
    assert client.get(f"/api/drafts?status=archive&fan_id={fan.id}").json()["items"][0]["status"] == "replaced"


def test_draft_reject_recover_delete(client: TestClient, seeded: Session) -> None:
    fan = seeded.scalar(select(Fan).where(Fan.status != "not_contactable"))
    did = client.post(f"/api/fans/{fan.id}/generate", json={"kind": "reply"}).json()["id"]
    assert client.post(f"/api/drafts/{did}/reject", json={"reason": "off tone"}).json()["status"] == "rejected"
    assert client.post(f"/api/drafts/{did}/reject", json={}).status_code == 409
    assert client.post(f"/api/drafts/{did}/recover").json()["status"] == "pending"
    assert client.delete(f"/api/drafts/{did}").status_code == 200
    assert client.post(f"/api/drafts/{did}/approve", json={}).status_code == 404


def test_settings_validation_and_persona_versions(client: TestClient) -> None:
    e = client.put("/api/settings/engine", json={"approval_mode": "auto", "pacing": "fast"}).json()
    assert e["approval_mode"] == "auto" and e["pacing"] == "fast"
    assert client.put("/api/settings/engine", json={"approval_mode": "yolo"}).status_code == 422
    assert client.put("/api/settings/persona", json={"age": 16}).status_code == 422  # adults only
    assert client.get("/api/settings/nope").status_code == 404
    client.put("/api/settings/persona", json={"bio": "new bio one"})
    client.put("/api/settings/persona", json={"bio": "new bio two"})
    prev = client.get("/api/persona/preview").json()
    assert "new bio two" in prev["persona_prompt"] and len(prev["versions"]) >= 2
    assert "Never claim to be human" in prev["safety_block"]


def test_rules_crud(client: TestClient) -> None:
    lst = client.get("/api/rules").json()
    assert len(lst["metrics"]) == 16 and len(lst["items"]) == 4 and not any(r["enabled"] for r in lst["items"])
    body = {"name": "x", "enabled": True, "action": "note", "note": "hi {total_spent}",
            "conditions": [{"metric": "total_spent", "op": "gte", "value": 5}]}
    r = client.post("/api/rules", json=body).json()
    assert client.put(f"/api/rules/{r['id']}", json={**body, "action": "explode"}).status_code == 422
    assert client.post("/api/rules", json={**body, "conditions": []}).status_code == 422
    assert client.delete(f"/api/rules/{r['id']}").status_code == 200


def test_ppv_crud_and_validation(client: TestClient, seeded: Session) -> None:
    tags = client.get("/api/ppv/tags").json()["items"]
    assert len(tags) == 5
    assert client.post("/api/ppv/tags", json={"name": tags[0]["name"].upper()}).status_code == 409
    body = {"name": "Test set", "description": "desc", "media_uuids": ["m1"], "price": 2.5}
    assert client.post("/api/ppv/templates", json=body).status_code == 422  # below $3
    assert client.post("/api/ppv/templates", json={**body, "media_uuids": []}).status_code == 422
    assert client.post("/api/ppv/templates", json={**body, "price": 9, "gate_min_spent": 50,
                                                   "gate_max_spent": 10}).status_code == 422
    t = client.post("/api/ppv/templates", json={**body, "price": 9, "tag_ids": [tags[0]["id"]]}).json()
    assert t["price"] == 9 and t["active"]
    assert client.post(f"/api/ppv/templates/{t['id']}/toggle").json()["active"] is False
    fan = seeded.scalar(select(Fan))
    assert client.post(f"/api/fans/{fan.id}/ppv-sales", json={"template_id": t["id"]}).json()["ok"]
    assert t["id"] in client.get(f"/api/fans/{fan.id}").json()["content"]["owned_template_ids"]
    assert client.delete(f"/api/ppv/tags/{tags[0]['id']}").status_code == 200
    seeded.expire_all()
    assert tags[0]["id"] not in seeded.get(PpvTemplate, t["id"]).tag_ids


def test_mock_simulator_and_purchase(client: TestClient, seeded: Session) -> None:
    client.put("/api/settings/engine", json={"enabled": True})
    fan = seeded.scalar(select(Fan).where(Fan.status != "not_contactable"))
    r = client.post("/api/mock/simulate-message", json={"fan_id": fan.id, "text": "hi!", "tip": 25})
    assert r.status_code == 200 and r.json()["sync"]["messages_added"] == 1
    seeded.expire_all()
    f = seeded.get(Fan, fan.id)
    assert f.tips_count >= 1 and f.tip_total_cents >= 2500
    assert any(a["category"] == "big_tip" for a in client.get("/api/alerts").json()["items"])
    assert client.post("/api/mock/simulate-purchase", json={"fan_id": fan.id, "template_id": 1}).status_code == 409


def test_reengage_endpoints(client: TestClient) -> None:
    assert "items" in client.get("/api/reengage/preview").json()
    r = client.post("/api/reengage/run?limit=2").json()
    assert r["drafted"] == 0 and "re-engagement disabled" in r["skipped"]
    client.put("/api/settings/reengage", json={"enabled": True, "active_within_days": None})
    r = client.post("/api/reengage/run?limit=2").json()
    assert r["drafted"] <= 2


def test_forget_fan_and_export(client: TestClient, seeded: Session) -> None:
    fan = seeded.scalar(select(Fan).where(Fan.status != "not_contactable"))
    client.patch(f"/api/fans/{fan.id}", json={"notes": "private"})
    exp = client.get("/api/export")
    assert exp.status_code == 200 and "private" in exp.text and "access_token" not in exp.text
    assert client.delete(f"/api/fans/{fan.id}/data").json()["ok"]
    d = client.get(f"/api/fans/{fan.id}").json()
    assert d["notes"] == "" and client.get(f"/api/conversations/{fan.id}/messages").json()["items"] == []


def test_logs(client: TestClient) -> None:
    assert client.get("/api/logs/audit").json()["items"]
    assert "items" in client.get("/api/logs/jobs").json()
    assert "items" in client.get("/api/logs/usage").json()


# ------------------------------------------------------------------------------------------------ webhooks
def test_webhook_signature_unit() -> None:
    body = b'{"id":"e1"}'
    t = int(time.time())
    h = f"t={t},v0={sign('s', t, body)}"
    assert verify_signature("s", h, body)
    assert not verify_signature("s", h, body + b" ")
    assert not verify_signature("other", h, body)
    assert not verify_signature("s", f"t={t - 1000},v0={sign('s', t - 1000, body)}", body)
    assert verify_signature("s", f"t={t},v0=deadbeef,{sign('s', t, body)}", body)  # rotation
    assert not verify_signature("s", None, body) and not verify_signature("", h, body)


def test_webhook_endpoint(client: TestClient, seeded: Session) -> None:
    probe = client.post("/api/webhooks/fanvue", json={"type": "fanvue.webhook.verification"})
    assert probe.status_code == 200
    body = json.dumps({"id": "evt-1", "type": "creator.message.received", "data": {"object": "message"}}).encode()
    t = int(time.time())
    assert client.post("/api/webhooks/fanvue", content=body,
                       headers={"X-Fanvue-Signature": f"t={t},v0=bad"}).status_code == 401
    good = {"X-Fanvue-Signature": f"t={t},v0={sign('whsec_test', t, body)}", "Content-Type": "application/json"}
    assert client.post("/api/webhooks/fanvue", content=body, headers=good).status_code == 200
    assert client.post("/api/webhooks/fanvue", content=body, headers=good).status_code == 200  # dedup
    seeded.expire_all()
    assert seeded.scalar(select(func.count()).select_from(WebhookEvent)) == 1
    assert seeded.scalar(select(func.count()).select_from(Job).where(Job.idempotency_key == "sync-webhook-evt-1")) == 1


# ------------------------------------------------------------------------------------------------ OAuth
def test_oauth_pkce_flow_and_rotation(seeded: Session) -> None:
    url = oauth.build_authorize_url(seeded)
    q = parse_qs(urlparse(url).query)
    assert url.startswith("https://auth.fanvue.com/oauth2/auth")
    assert q["code_challenge_method"] == ["S256"] and len(q["state"][0]) >= 32
    assert "offline_access" in q["scope"][0] and q["redirect_uri"][0].endswith("/api/fanvue/oauth/callback")
    calls: list[dict[str, str]] = []

    def token_ep(req: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
        calls.append(form)
        assert req.headers["authorization"].startswith("Basic ")  # client_secret_basic
        if form["grant_type"] == "authorization_code":
            assert len(form["code_verifier"]) >= 43
            return httpx.Response(200, json={"access_token": "A1", "refresh_token": "R1", "expires_in": 3600,
                                             "scope": "read:chat"})
        if form["refresh_token"] == "R1":
            return httpx.Response(200, json={"access_token": "A2", "refresh_token": "R2", "expires_in": 3600})
        return httpx.Response(400, json={"error": "invalid_grant"})

    tr = httpx.MockTransport(token_ep)
    with pytest.raises(ValueError):
        oauth.exchange_code(seeded, "wrong-state", "code", tr)
    oauth.exchange_code(seeded, q["state"][0], "code", tr)
    seeded.commit()
    conn = seeded.get(FanvueConnection, 1)
    assert conn.status == "connected" and "A1" not in (conn.access_token_enc or "")  # encrypted at rest
    assert oauth.access_token(seeded, tr) == "A1"
    conn.expires_at = utcnow() - timedelta(seconds=1)
    seeded.commit()
    assert oauth.access_token(seeded, tr) == "A2"  # rotated
    conn.expires_at = utcnow() - timedelta(seconds=1)
    seeded.commit()
    # the rotated R2 is used (never the spent R1); the fake server rejects it -> reconnect required
    with pytest.raises(NeedsReconnect):
        oauth.access_token(seeded, tr)
    assert [c.get("refresh_token") for c in calls if c["grant_type"] == "refresh_token"] == ["R1", "R2"]
    assert seeded.get(FanvueConnection, 1).needs_reconnect


def test_oauth_invalid_grant_requires_reconnect(seeded: Session) -> None:
    from app.security import encrypt

    conn = oauth.get_connection(seeded)
    conn.access_token_enc, conn.refresh_token_enc = encrypt("A"), encrypt("stale")
    conn.expires_at = utcnow() - timedelta(seconds=5)
    seeded.commit()
    tr = httpx.MockTransport(lambda r: httpx.Response(400, json={"error": "invalid_grant"}))
    with pytest.raises(NeedsReconnect):
        oauth.access_token(seeded, tr)
    assert seeded.get(FanvueConnection, 1).needs_reconnect


# ------------------------------------------------------------------------------------------------ live client contract
def _live(handler) -> LiveFanvueClient:  # type: ignore[no-untyped-def]
    return LiveFanvueClient(token_provider=lambda: "TOKEN", transport=httpx.MockTransport(handler), max_retries=1)


def test_live_client_requests_match_official_api() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        p = req.url.path
        if p == "/v1/users/me":
            return httpx.Response(200, json={"uuid": "c1", "handle": "me", "displayName": "Me"})
        if p == "/v1/chats":
            return httpx.Response(200, json={"data": [
                {"user": {"uuid": "f1", "handle": "fan1", "displayName": "Fan One"}, "isCreator": False,
                 "lastMessageAt": "2026-11-01T10:00:00Z", "unreadMessagesCount": 2},
                {"user": {"uuid": "c2", "handle": "other", "displayName": "Creator"}, "isCreator": True}],
                "nextCursor": "abc"})
        if p == "/v1/chats/f1/messages":
            return httpx.Response(200, json={"data": [
                {"uuid": "m2", "text": "hey", "sentAt": "2026-11-01T10:00:00Z", "sender": {"uuid": "f1"}},
                {"uuid": "m1", "text": "hi", "sentAt": "2026-11-01T09:00:00Z", "sender": {"uuid": "c1"}}]})
        if p == "/v1/insights/fans/f1":
            return httpx.Response(200, json={"status": "subscriber", "spending": {
                "total": {"gross": 4599}, "maxSinglePayment": {"gross": 2000}, "lastPurchaseAt": None}})
        if p == "/v1/chats/f1/message":
            return httpx.Response(201, json={"messageUuid": "new1"})
        return httpx.Response(404)

    c = _live(handler)
    assert c.get_me().handle == "me"
    chats, cur = c.list_chats()
    assert cur == "abc" and [ch.fan.uuid for ch in chats] == ["f1"] and chats[0].unread_count == 2
    msgs = c.get_messages("f1")
    assert [m.sender for m in msgs] == ["fan", "creator"]
    ins = c.get_fan_insight("f1")
    assert ins.spent_cents == 4599 and ins.status == "subscriber"
    assert c.send_message("f1", "hello", media_uuids=["x"], price_cents=500) == "new1"
    send_req = seen[-1]
    assert json.loads(send_req.content) == {"text": "hello", "mediaUuids": ["x"], "price": 500}
    for r in seen:
        assert r.headers["authorization"] == "Bearer TOKEN"
        assert r.headers["x-fanvue-api-version"] == "2025-06-26"
    assert "markAsRead=false" in str(seen[2].url)


def test_live_client_errors_and_retry() -> None:
    n = {"c": 0}

    def flaky(req: httpx.Request) -> httpx.Response:
        n["c"] += 1
        return httpx.Response(429, headers={"Retry-After": "0"}) if n["c"] == 1 else httpx.Response(
            200, json={"uuid": "u", "handle": "h", "displayName": "d"})

    assert _live(flaky).get_me().uuid == "u" and n["c"] == 2
    with pytest.raises(NotContactable):
        _live(lambda r: httpx.Response(400, json={"message": "User is not contactable"})).send_message("f", "x")
    with pytest.raises(NeedsReconnect):
        _live(lambda r: httpx.Response(401)).get_me()
    with pytest.raises(Exception, match="300"):
        _live(lambda r: httpx.Response(201, json={})).send_message("f", "x", price_cents=100)


# ------------------------------------------------------------------------------------------------ migrations
def test_migrations_up_down_up(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.db import make_engine
    from app.migrate import downgrade, upgrade

    url = f"sqlite:///{tmp_path / 'm.db'}"
    upgrade(url)
    names = set(inspect(make_engine(url)).get_table_names())
    assert {"fans", "messages", "drafts", "jobs", "ppv_templates", "settings"} <= names
    downgrade(url, "base")
    assert set(inspect(make_engine(url)).get_table_names()) <= {"alembic_version"}
    upgrade(url)
    assert "fans" in inspect(make_engine(url)).get_table_names()
