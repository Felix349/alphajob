from datetime import UTC, date, datetime, timedelta

import pytest

APP = {"company": "字节跳动", "role": "后端开发工程师（校招）"}


def iso(dt: datetime) -> str:
    return dt.isoformat()


@pytest.fixture
async def alice(user_client):
    return await user_client("alice@example.com")


@pytest.fixture
async def bob(user_client):
    return await user_client("bob@example.com")


async def create_app(client, **overrides):
    resp = await client.post("/api/applications", json={**APP, **overrides})
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------- 投递记录 CRUD ----------


async def test_requires_login(client):
    assert (await client.get("/api/applications")).status_code == 401
    assert (await client.post("/api/applications", json=APP)).status_code == 401


async def test_create_defaults_to_wishlist(alice):
    app = await create_app(alice)
    assert app["stage"] == "wishlist"
    assert app["applied_at"] is None
    assert app["events"] == [] and app["next_event"] is None


async def test_create_in_applied_stage_records_today(alice):
    app = await create_app(alice, stage="applied")
    assert app["applied_at"] == date.today().isoformat()


async def test_new_cards_go_to_top_of_column(alice):
    first = await create_app(alice, company="A")
    second = await create_app(alice, company="B")
    assert second["position"] < first["position"]
    listed = (await alice.get("/api/applications")).json()
    assert [a["company"] for a in listed] == ["B", "A"]


async def test_list_filters(alice):
    await create_app(alice, company="腾讯", role="算法工程师")
    await create_app(alice, company="阿里巴巴", role="前端开发", stage="applied")
    by_stage = (await alice.get("/api/applications", params={"stage": "applied"})).json()
    assert [a["company"] for a in by_stage] == ["阿里巴巴"]
    by_text = (await alice.get("/api/applications", params={"q": "算法"})).json()
    assert [a["company"] for a in by_text] == ["腾讯"]


async def test_update_and_jd_parsed_roundtrip(alice):
    app = await create_app(alice)
    parsed = {
        "company": "字节跳动",
        "role": "后端开发",
        "location": "北京",
        "job_type": "校招",
        "salary": None,
        "deadline": "2026-12-01",
        "responsibilities": ["负责推荐系统后端"],
        "requirements": ["熟悉 Go 或 Java"],
        "bonus": [],
        "tech_stack": ["Go", "Kafka"],
        "summary": "看重扎实的后端基础",
    }
    resp = await alice.patch(
        f"/api/applications/{app['id']}", json={"notes": "内推人：张三", "jd_parsed": parsed}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["notes"] == "内推人：张三"
    assert body["jd_parsed"]["tech_stack"] == ["Go", "Kafka"]
    assert body["company"] == APP["company"]  # 没传的字段保持不变


async def test_moving_out_of_wishlist_sets_applied_date_and_top_position(alice):
    existing = await create_app(alice, company="已在列中", stage="applied")
    app = await create_app(alice)
    resp = await alice.patch(f"/api/applications/{app['id']}", json={"stage": "applied"})
    body = resp.json()
    assert body["stage"] == "applied"
    assert body["applied_at"] == date.today().isoformat()
    assert body["position"] < existing["position"]


async def test_explicit_position_is_respected(alice):
    app = await create_app(alice)
    resp = await alice.patch(
        f"/api/applications/{app['id']}", json={"stage": "interviewing", "position": 1536.5}
    )
    assert resp.json()["position"] == 1536.5


async def test_rejects_invalid_stage(alice):
    app = await create_app(alice)
    resp = await alice.patch(f"/api/applications/{app['id']}", json={"stage": "unknown"})
    assert resp.status_code == 422


async def test_delete_cascades_events(alice):
    app = await create_app(alice)
    start = datetime.now(UTC) + timedelta(days=1)
    await alice.post(
        f"/api/applications/{app['id']}/events",
        json={"type": "interview", "title": "一面", "start_at": iso(start)},
    )
    assert (await alice.delete(f"/api/applications/{app['id']}")).status_code == 204
    assert (await alice.get(f"/api/applications/{app['id']}")).status_code == 404
    window = {"start": iso(start - timedelta(days=2)), "end": iso(start + timedelta(days=2))}
    assert (await alice.get("/api/events", params=window)).json() == []


# ---------- 数据隔离：用户 A 永远看不到、改不了用户 B 的数据 ----------


async def test_users_cannot_access_each_other(alice, bob):
    app = await create_app(alice)
    event = (
        await alice.post(
            f"/api/applications/{app['id']}/events",
            json={
                "type": "interview",
                "title": "一面",
                "start_at": iso(datetime.now(UTC) + timedelta(days=1)),
            },
        )
    ).json()
    url = f"/api/applications/{app['id']}"

    assert (await bob.get("/api/applications")).json() == []
    assert (await bob.get(url)).status_code == 404
    assert (await bob.patch(url, json={"company": "被篡改"})).status_code == 404
    assert (await bob.delete(url)).status_code == 404
    new_event = {"type": "other", "title": "x", "start_at": iso(datetime.now(UTC))}
    assert (await bob.post(f"{url}/events", json=new_event)).status_code == 404
    assert (await bob.patch(f"/api/events/{event['id']}", json={"title": "x"})).status_code == 404
    assert (await bob.delete(f"/api/events/{event['id']}")).status_code == 404

    # Alice 的数据完好无损
    detail = (await alice.get(url)).json()
    assert detail["company"] == APP["company"] and len(detail["events"]) == 1


# ---------- 日程事件 ----------


async def test_event_validation(alice):
    app = await create_app(alice)
    url = f"/api/applications/{app['id']}/events"
    start = datetime.now(UTC) + timedelta(days=1)
    bad_range = {
        "type": "interview",
        "title": "一面",
        "start_at": iso(start),
        "end_at": iso(start - timedelta(hours=1)),
    }
    assert (await alice.post(url, json=bad_range)).status_code == 422
    # 不带时区的时间会造成歧义，必须拒绝
    naive = {"type": "interview", "title": "一面", "start_at": "2026-12-01T10:00:00"}
    assert (await alice.post(url, json=naive)).status_code == 422


async def test_next_event_is_nearest_upcoming(alice):
    app = await create_app(alice)
    url = f"/api/applications/{app['id']}/events"
    now = datetime.now(UTC)
    for title, delta in [("过去的笔试", -2), ("二面", 5), ("一面", 2)]:
        start = iso(now + timedelta(days=delta))
        await alice.post(url, json={"type": "interview", "title": title, "start_at": start})
    listed = (await alice.get("/api/applications")).json()
    assert listed[0]["next_event"]["title"] == "一面"
    detail = (await alice.get(f"/api/applications/{app['id']}")).json()
    assert [e["title"] for e in detail["events"]] == ["过去的笔试", "一面", "二面"]


async def test_update_event_rejects_end_before_start(alice):
    app = await create_app(alice)
    start = datetime.now(UTC) + timedelta(days=1)
    event = (
        await alice.post(
            f"/api/applications/{app['id']}/events",
            json={"type": "interview", "title": "一面", "start_at": iso(start)},
        )
    ).json()
    resp = await alice.patch(
        f"/api/events/{event['id']}", json={"end_at": iso(start - timedelta(hours=1))}
    )
    assert resp.status_code == 422


async def test_calendar_range_query(alice):
    app = await create_app(alice, company="美团")
    url = f"/api/applications/{app['id']}/events"
    base = datetime(2026, 12, 1, 10, 0, tzinfo=UTC)
    await alice.post(url, json={"type": "written_test", "title": "笔试", "start_at": iso(base)})
    await alice.post(
        url,
        json={"type": "interview", "title": "下个月", "start_at": iso(base + timedelta(days=40))},
    )
    resp = await alice.get(
        "/api/events",
        params={"start": iso(base - timedelta(days=1)), "end": iso(base + timedelta(days=30))},
    )
    events = resp.json()
    assert [e["title"] for e in events] == ["笔试"]
    assert events[0]["company"] == "美团" and events[0]["stage"] == "wishlist"


async def test_calendar_rejects_bad_ranges(alice):
    now = datetime.now(UTC)
    backwards = {"start": iso(now), "end": iso(now - timedelta(days=1))}
    too_long = {"start": iso(now), "end": iso(now + timedelta(days=500))}
    assert (await alice.get("/api/events", params=backwards)).status_code == 422
    assert (await alice.get("/api/events", params=too_long)).status_code == 422
