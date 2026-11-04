import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings

COOKIE = get_settings().cookie_name
EMAIL = "user0@example.com"
PASSWORD = "correct-horse-battery"


async def register(client, email=EMAIL, password=PASSWORD, **extra):
    return await client.post(
        "/api/auth/register", json={"email": email, "password": password, **extra}
    )


# ---------- 注册 ----------


async def test_register_success_logs_in(client):
    resp = await register(client, display_name="User 0")
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == EMAIL
    assert body["display_name"] == "User 0"
    assert "password_hash" not in body and "password" not in body
    # 注册后自动登录：Cookie 已下发且是 httpOnly
    set_cookie = resp.headers["set-cookie"]
    assert COOKIE in set_cookie and "HttpOnly" in set_cookie and "SameSite=lax" in set_cookie
    me = await client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["email"] == EMAIL


async def test_register_duplicate_email_is_case_insensitive(client):
    assert (await register(client)).status_code == 201
    resp = await register(client, email=EMAIL.upper())
    assert resp.status_code == 409


async def test_register_rejects_short_password(client):
    resp = await register(client, password="short")
    assert resp.status_code == 422


async def test_register_rejects_invalid_email(client):
    resp = await register(client, email="not-an-email")
    assert resp.status_code == 422


# ---------- 登录 ----------


async def test_login_success(make_client):
    await register(await make_client())
    fresh = await make_client()  # 一个没有任何 Cookie 的新会话
    resp = await fresh.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert resp.status_code == 200
    assert (await fresh.get("/api/auth/me")).status_code == 200


async def test_login_wrong_password_and_unknown_email_look_the_same(make_client):
    await register(await make_client())
    fresh = await make_client()
    wrong_pw = await fresh.post("/api/auth/login", json={"email": EMAIL, "password": "wrong-pass"})
    unknown = await fresh.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json() == unknown.json()  # 不泄露邮箱是否注册过
    assert COOKIE not in fresh.cookies


# ---------- 当前用户 / 登出 ----------


async def test_me_requires_login(client):
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_logout_clears_session(client):
    await register(client)
    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_tampered_token_rejected(client):
    await register(client)
    token = client.cookies[COOKIE]
    client.cookies.set(COOKIE, token[:-2] + ("AA" if not token.endswith("AA") else "BB"))
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_expired_token_rejected(client):
    resp = await register(client)
    s = get_settings()
    past = datetime.now(UTC) - timedelta(days=1)
    expired = jwt.encode(
        {"sub": resp.json()["id"], "iat": past, "exp": past + timedelta(minutes=1)},
        s.jwt_secret,
        algorithm=s.jwt_algorithm,
    )
    client.cookies.set(COOKIE, expired)
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_token_for_deleted_or_unknown_user_rejected(client):
    s = get_settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "iat": now, "exp": now + timedelta(hours=1)},
        s.jwt_secret,
        algorithm=s.jwt_algorithm,
    )
    client.cookies.set(COOKIE, token)
    assert (await client.get("/api/auth/me")).status_code == 401
