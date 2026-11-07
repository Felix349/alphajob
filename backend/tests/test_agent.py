"""求职 Agent：工具调用循环、写操作确认、计划生成。大模型用“按剧本回复”的假实现。"""

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.agent.context import AgentContext, resolve_tz
from app.agent.loop import MAX_STEPS, TOO_MANY_STEPS
from app.api.deps import require_llm
from app.llm import AssistantTurn, LLMError, StructuredResult, ToolCall
from app.main import app
from app.models import AgentAction, AgentPlan, Event, LLMCallLog, User
from app.schemas.agent import TodayPlan, WeekPlan
from app.services import plan as plan_service
from tests.conftest import TestSessionLocal


class ScriptedSession:
    def __init__(self, llm, turns):
        self.llm, self.turns = llm, list(turns)

    async def step(self) -> AssistantTurn:
        if self.llm.error:
            raise self.llm.error
        if not self.turns:  # 剧本用完了还在要：模拟“一直调用工具停不下来”
            return AssistantTurn(
                "", [ToolCall(f"loop{len(self.llm.results)}", "list_events", {})], 1, 1
            )
        turn = self.turns.pop(0)
        return turn(self.llm) if callable(turn) else turn

    def add_tool_results(self, results):
        self.llm.results.append(results)


class ScriptedLLM:
    provider, model = "fake", "fake-model"

    def __init__(self, turns=(), plan=None, error=None):
        self.turns, self.plan, self.error = turns, plan, error
        self.results, self.systems = [], []

    def tool_session(self, *, system, history, tools):
        self.systems.append(system)
        self.tool_names = [t.name for t in tools]
        return ScriptedSession(self, self.turns)

    async def structured(self, *, system, user, schema, effort="medium", max_tokens=4096):
        self.plan_prompt = user
        return StructuredResult(
            self.plan(schema) if callable(self.plan) else self.plan, "fake", "fake-model", 500, 300
        )


def call(name, **args) -> AssistantTurn:
    return AssistantTurn("", [ToolCall(f"c-{name}", name, args)], 100, 20)


def say(text) -> AssistantTurn:
    return AssistantTurn(text, [], 100, 20)


@pytest.fixture
def use_llm():
    def _use(fake):
        app.dependency_overrides[require_llm] = lambda: fake
        return fake

    yield _use
    app.dependency_overrides.pop(require_llm, None)


@pytest.fixture
async def alice(user_client):
    return await user_client("alice@example.com")


async def new_app(client, company="北辰云", stage="applied") -> str:
    resp = await client.post(
        "/api/applications", json={"company": company, "role": "Agent 开发", "stage": stage}
    )
    return resp.json()["id"]


async def chat(client, text, timezone="Asia/Shanghai") -> list[tuple[str, dict]]:
    events, raw = [], ""
    body = {"messages": [{"role": "user", "content": text}], "timezone": timezone}
    async with client.stream("POST", "/api/agent/chat", json=body) as resp:
        assert resp.status_code == 200, await resp.aread()
        async for chunk in resp.aiter_text():
            raw += chunk.replace("\r\n", "\n")
            while "\n\n" in raw:
                block, raw = raw.split("\n\n", 1)
                name = next(
                    (ln[6:].strip() for ln in block.split("\n") if ln.startswith("event:")), ""
                )
                data = "".join(ln[5:].strip() for ln in block.split("\n") if ln.startswith("data:"))
                if data:
                    events.append((name, json.loads(data)))
    return events


# ---------- 读工具与循环 ----------


async def test_read_tool_then_answer(alice, use_llm):
    await new_app(alice)
    llm = use_llm(ScriptedLLM([call("list_applications"), say("你有 1 条投递：北辰云。")]))
    events = await chat(alice, "我投了哪些公司？")

    assert [n for n, _ in events] == ["tool_call", "tool_result", "message"]
    assert events[1][1]["summary"] == "返回 1 条" and events[1][1]["ok"] is True
    assert events[-1][1]["text"] == "你有 1 条投递：北辰云。"
    # 工具结果真的回传给了模型
    [[result]] = llm.results
    assert "北辰云" in result.content and not result.is_error
    assert "Asia/Shanghai" in llm.systems[0]  # 系统提示词里带上了用户时区
    assert len(llm.tool_names) == 11

    async with TestSessionLocal() as s:
        [log] = (await s.execute(select(LLMCallLog))).scalars().all()
    assert log.feature == "agent_chat" and log.input_tokens == 200 and log.success


async def test_errors_are_fed_back_to_the_model(alice, use_llm):
    """未知工具、参数错误、id 不存在：都作为错误结果交还给模型，而不是中断对话。"""
    llm = use_llm(
        ScriptedLLM(
            [
                call("no_such_tool"),
                call("update_application_stage", stage="offer"),  # 缺 application_id
                call("get_application", application_id="00000000-0000-0000-0000-000000000000"),
                say("抱歉，没找到这条投递。"),
            ]
        )
    )
    events = await chat(alice, "随便")
    results = [d for n, d in events if n == "tool_result"]
    assert len(results) == 3 and all(r["ok"] is False for r in results)
    assert all(r[0].is_error for r in llm.results)
    assert "没有名为" in llm.results[0][0].content
    assert "参数不正确" in llm.results[1][0].content
    assert events[-1][0] == "message"


async def test_step_limit_prevents_infinite_tool_loops(alice, use_llm):
    use_llm(ScriptedLLM([]))  # 剧本为空：模型每次都要求再调工具
    events = await chat(alice, "随便")
    assert sum(1 for n, _ in events if n == "tool_call") == MAX_STEPS
    assert events[-1] == ("message", {"text": TOO_MANY_STEPS})


async def test_llm_failure_sends_error_event(alice, use_llm):
    use_llm(ScriptedLLM(error=LLMError("deepseek 请求过于频繁")))
    events = await chat(alice, "随便")
    assert events[-1][0] == "error" and "频繁" in events[-1][1]["detail"]
    async with TestSessionLocal() as s:
        [log] = (await s.execute(select(LLMCallLog))).scalars().all()
    assert not log.success


async def test_chat_request_must_end_with_user_message(alice, use_llm):
    use_llm(ScriptedLLM())
    body = {
        "messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    }
    assert (await alice.post("/api/agent/chat", json=body)).status_code == 422


# ---------- 写操作：只提议，确认后才执行 ----------


async def test_write_tool_creates_proposal_and_only_runs_after_confirm(alice, use_llm):
    app_id = await new_app(alice)
    llm = use_llm(
        ScriptedLLM(
            [
                call("update_application_stage", application_id=app_id, stage="interviewing"),
                say("请在下方确认。"),
            ]
        )
    )
    events = await chat(alice, "把北辰云改成面试中")
    [(_, proposal)] = [(n, d) for n, d in events if n == "proposal"]
    assert (
        "北辰云" in proposal["description"]
        and "已投递" in proposal["description"]
        and "面试中" in proposal["description"]
    )
    assert "等待用户" in llm.results[0][0].content  # 模型知道操作还没生效

    # 确认之前，数据没有任何变化
    assert (await alice.get(f"/api/applications/{app_id}")).json()["stage"] == "applied"

    confirmed = await alice.post(f"/api/agent/actions/{proposal['id']}/confirm")
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "done"
    assert (await alice.get(f"/api/applications/{app_id}")).json()["stage"] == "interviewing"
    # 重复确认不会执行两次
    assert (await alice.post(f"/api/agent/actions/{proposal['id']}/confirm")).status_code == 409


async def test_cancelled_proposal_changes_nothing(alice, use_llm):
    app_id = await new_app(alice)
    use_llm(
        ScriptedLLM(
            [
                call("update_application_stage", application_id=app_id, stage="ended"),
                say("请确认。"),
            ]
        )
    )
    proposal = next(d for n, d in await chat(alice, "放弃北辰云") if n == "proposal")
    resp = await alice.post(f"/api/agent/actions/{proposal['id']}/cancel")
    assert resp.json()["status"] == "cancelled"
    assert (await alice.get(f"/api/applications/{app_id}")).json()["stage"] == "applied"
    assert (await alice.post(f"/api/agent/actions/{proposal['id']}/confirm")).status_code == 409


async def test_create_event_uses_user_local_time(alice, use_llm):
    app_id = await new_app(alice)
    use_llm(
        ScriptedLLM(
            [
                call(
                    "create_event",
                    application_id=app_id,
                    type="interview",
                    title="二面",
                    start_at="2026-11-07T14:00",
                ),
                say("请确认。"),
            ]
        )
    )
    proposal = next(
        d
        for n, d in await chat(alice, "周五下午两点二面", timezone="Asia/Shanghai")
        if n == "proposal"
    )
    assert "11-07 周六 14:00" in proposal["description"] or "11-07" in proposal["description"]
    await alice.post(f"/api/agent/actions/{proposal['id']}/confirm")
    async with TestSessionLocal() as s:
        [event] = (await s.execute(select(Event))).scalars().all()
    # 不带时区的“14:00”按北京时间理解，存进数据库是 UTC 06:00
    assert event.start_at.astimezone(UTC) == datetime(2026, 11, 7, 6, 0, tzinfo=UTC)


async def test_agent_cannot_propose_actions_on_other_users_data(alice, user_client, use_llm):
    app_id = await new_app(alice)
    bob = await user_client("bob@example.com")
    llm = use_llm(
        ScriptedLLM(
            [
                call("update_application_stage", application_id=app_id, stage="offer"),
                say("没找到。"),
            ]
        )
    )
    events = await chat(bob, "把这条改成 offer")
    assert not any(n == "proposal" for n, _ in events)
    assert llm.results[0][0].is_error  # 对模型来说，别人的数据“不存在”
    async with TestSessionLocal() as s:
        assert (await s.execute(select(AgentAction))).scalars().all() == []


async def test_cannot_confirm_other_users_action(alice, user_client, use_llm):
    app_id = await new_app(alice)
    use_llm(
        ScriptedLLM(
            [
                call("update_application_stage", application_id=app_id, stage="offer"),
                say("请确认。"),
            ]
        )
    )
    proposal = next(d for n, d in await chat(alice, "改成 offer") if n == "proposal")
    bob = await user_client("bob@example.com")
    assert (await bob.post(f"/api/agent/actions/{proposal['id']}/confirm")).status_code == 404
    assert (await alice.get(f"/api/applications/{app_id}")).json()["stage"] == "applied"


async def test_confirm_reports_failure_when_target_was_deleted(alice, use_llm):
    app_id = await new_app(alice)
    use_llm(
        ScriptedLLM(
            [
                call("update_application_stage", application_id=app_id, stage="offer"),
                say("请确认。"),
            ]
        )
    )
    proposal = next(d for n, d in await chat(alice, "改成 offer") if n == "proposal")
    await alice.delete(f"/api/applications/{app_id}")  # 提议之后、确认之前，投递被删掉了
    resp = await alice.post(f"/api/agent/actions/{proposal['id']}/confirm")
    assert resp.status_code == 200 and resp.json()["status"] == "failed"


# ---------- 计划 ----------


def _today_plan(app_id: str | None, foreign: str = "11111111-1111-1111-1111-111111111111"):
    return TodayPlan.model_validate(
        {
            "focus": "准备北辰云二面",
            "items": [
                {
                    "title": "复习记忆淘汰策略",
                    "reason": "周五北辰云二面",
                    "minutes": 60,
                    "priority": 1,
                    "application_id": app_id,
                },
                {
                    "title": "刷两道题",
                    "reason": "题库待复习",
                    "minutes": 999,
                    "priority": 2,
                    "application_id": foreign,
                },
            ],
        }
    )


async def test_today_plan_generate_get_and_toggle(alice, use_llm):
    app_id = await new_app(alice)
    llm = use_llm(ScriptedLLM(plan=_today_plan(app_id)))
    assert (await alice.get("/api/agent/plan", params={"kind": "today"})).json() is None

    created = await alice.post(
        "/api/agent/plan", json={"kind": "today", "timezone": "Asia/Shanghai"}
    )
    assert created.status_code == 201, created.text
    plan = created.json()
    items = plan["plan"]["items"]
    assert items[0]["application_id"] == app_id
    assert items[1]["application_id"] is None  # 不属于当前用户的 id 被清掉
    assert items[1]["minutes"] == 180  # 用时被夹到合理范围
    assert "<context>" in llm.plan_prompt and "北辰云" in llm.plan_prompt

    fetched = (await alice.get("/api/agent/plan", params={"kind": "today"})).json()
    assert fetched["id"] == plan["id"]
    toggled = await alice.patch(f"/api/agent/plan/{plan['id']}", json={"index": 1, "done": True})
    assert toggled.json()["done_items"] == [1]
    assert (
        await alice.patch(f"/api/agent/plan/{plan['id']}", json={"index": 9, "done": True})
    ).status_code == 404


async def test_week_plan(alice, use_llm):
    week = WeekPlan.model_validate(
        {
            "overview": "周五二面",
            "key_dates": ["周五 14:00 二面"],
            "days": [{"date": "2026-11-02", "focus": "复习", "tasks": ["复习"]}] * 7,
        }
    )
    use_llm(ScriptedLLM(plan=week))
    created = (await alice.post("/api/agent/plan", json={"kind": "week"})).json()
    assert created["kind"] == "week" and len(created["plan"]["days"]) == 7
    assert date.fromisoformat(created["plan_date"]).weekday() == 0  # 本周计划挂在周一


async def test_stale_plan_is_not_returned(alice, use_llm):
    use_llm(ScriptedLLM(plan=_today_plan(None)))
    plan_id = (await alice.post("/api/agent/plan", json={"kind": "today"})).json()["id"]
    async with TestSessionLocal() as s:
        p = await s.get(AgentPlan, plan_id)
        p.plan_date = p.plan_date - timedelta(days=1)  # 变成“昨天的计划”
        await s.commit()
    assert (await alice.get("/api/agent/plan", params={"kind": "today"})).json() is None


async def test_plan_context_flags_interviews_that_need_review(alice):
    app_id = await new_app(alice)
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    await alice.post(
        f"/api/applications/{app_id}/events",
        json={"type": "interview", "title": "一面", "start_at": past},
    )
    async with TestSessionLocal() as s:
        user = (await s.execute(select(User))).scalar_one()
        ctx = AgentContext(s, user, resolve_tz("Asia/Shanghai"))
        context = await plan_service.gather_context(ctx, "today")
    assert context["interviews_to_review"] == [
        {"company": "北辰云", "title": "一面", "application_id": app_id}
    ]
    assert context["active_applications"][0]["stage"] == "已投递"


def test_invalid_timezone_falls_back_to_default():
    assert str(resolve_tz("Not/AZone")) == "Asia/Shanghai"
    assert str(resolve_tz("America/New_York")) == "America/New_York"
