"""岗位匹配分析（SSE 流式）与备考清单。大模型全部用假实现。"""

import json
import uuid

import pytest
from sqlalchemy import select

from app.api.deps import require_llm
from app.llm import LLMError, StreamDone, StreamReset, StructuredResult, TextDelta
from app.main import app
from app.models import LLMCallLog, MatchReport
from app.schemas.match import MatchAnalysis, RequirementMatch, compute_score
from app.services.match import MATCH_MAX_TOKENS
from tests.conftest import TestSessionLocal

RESUME = "# 张三\n硕士，研究方向 LLM Agent。\n项目：用 LangGraph 搭建多 Agent 论文助手，支持工具调用与长期记忆。"
JD = "Agent 开发工程师（校招）。要求：熟悉 Python；理解 Planning、Memory、Tool Use；有 RAG 经验优先。"

ANALYSIS = MatchAnalysis.model_validate(
    {
        "summary": "Agent 方向对口，RAG 工程经验不足。",
        "highlights": ["LangGraph 多 Agent 项目"],
        "requirements": [
            {
                "requirement": "理解 Agent 机制",
                "importance": "required",
                "level": "strong",
                "evidence": "LangGraph 多 Agent 论文助手",
                "advice": "讲清记忆模块设计",
            },
            {
                "requirement": "RAG 经验",
                "importance": "preferred",  # JD：有 RAG 经验优先
                "level": "missing",
                "evidence": None,
                "advice": "做一个小型 RAG Demo",
            },
        ],
        "prep_items": [
            {"content": "复习 LangGraph 状态机设计", "category": "project", "priority": 2},
            {"content": "动手实现一个最小 RAG", "category": "knowledge", "priority": 1},
        ],
        "interview_questions": ["你的记忆模块怎么做淘汰？"],
        "resume_edits": [
            {
                "section": "项目经历：多 Agent 论文助手",
                "original": "项目：用 LangGraph 搭建多 Agent 论文助手，支持工具调用与长期记忆。",
                "suggestion": "基于 LangGraph 设计多 Agent 论文助手，实现 Tool Use 与长期 Memory，"
                "支撑【待补充：处理论文数量】篇论文的检索与总结",
                "reason": "JD 点名 Tool Use 和 Memory，用 JD 的关键词描述已有经历",
            },
        ],
    }
)


class FakeStreamLLM:
    provider = "fake"
    model = "fake-model"

    def __init__(self, analysis=ANALYSIS, *, reset=False, error: Exception | None = None):
        self.analysis, self.reset, self.error, self.prompts = analysis, reset, error, []

    async def stream_structured(self, *, system, user, schema, effort="medium", max_tokens=8192):
        self.prompts.append(user)
        self.max_tokens = max_tokens
        text = self.analysis.model_dump_json()
        for i in range(0, len(text), 40):  # 模拟逐段生成
            yield TextDelta(text[i : i + 40])
            if self.error and i > 0:
                raise self.error
        if self.reset:
            yield StreamReset("输出格式有误，正在修正")
        yield StreamDone(StructuredResult(self.analysis, "fake", "fake-model", 900, 400))


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


async def setup_app(client, *, resume=True, jd=True) -> str:
    if resume:
        await client.put("/api/resume", json={"content_md": RESUME})
    body = {"company": "北辰云", "role": "Agent 开发工程师", **({"jd_text": JD} if jd else {})}
    return (await client.post("/api/applications", json=body)).json()["id"]


async def run_match(
    client, app_id: str, notes: str | None = None, resume_language: str | None = None
) -> list[tuple[str, dict]]:
    """调用 SSE 接口，把事件流解析成 [(事件名, 数据)]。sse-starlette 默认用 \\r\\n 分隔。"""
    events = []
    url = f"/api/applications/{app_id}/match-report"
    body = {"notes": notes, "resume_language": resume_language}
    async with client.stream("POST", url, json=body) as resp:
        assert resp.status_code == 200, await resp.aread()
        assert resp.headers["content-type"].startswith("text/event-stream")
        buffer = ""
        async for chunk in resp.aiter_text():
            buffer += chunk.replace("\r\n", "\n")
            while "\n\n" in buffer:
                block, buffer = buffer.split("\n\n", 1)
                name, data = "message", ""
                for line in block.split("\n"):
                    if line.startswith("event:"):
                        name = line[6:].strip()
                    elif line.startswith("data:"):
                        data += line[5:].strip()
                if data:
                    events.append((name, json.loads(data)))
    return events


# ---------- 前置条件 ----------


async def test_requires_resume_and_jd(alice, use_llm):
    use_llm(FakeStreamLLM())
    no_resume = await setup_app(alice, resume=False)
    resp = await alice.post(f"/api/applications/{no_resume}/match-report", json={})
    assert resp.status_code == 400 and "简历" in resp.json()["detail"]

    await alice.put("/api/resume", json={"content_md": RESUME})
    no_jd = await setup_app(alice, jd=False)
    resp = await alice.post(f"/api/applications/{no_jd}/match-report", json={})
    assert resp.status_code == 400 and "岗位描述" in resp.json()["detail"]


async def test_cannot_analyse_or_read_other_users_application(alice, user_client, use_llm):
    use_llm(FakeStreamLLM())
    app_id = await setup_app(alice)
    bob = await user_client("bob@example.com")
    await bob.put("/api/resume", json={"content_md": RESUME})
    assert (await bob.post(f"/api/applications/{app_id}/match-report", json={})).status_code == 404
    assert (await bob.get(f"/api/applications/{app_id}/match-report")).status_code == 404
    assert (await bob.get(f"/api/applications/{app_id}/prep-items")).status_code == 404


# ---------- 流式生成 ----------


async def test_stream_emits_deltas_then_done_and_persists(alice, use_llm):
    fake = use_llm(FakeStreamLLM())
    app_id = await setup_app(alice)
    events = await run_match(alice, app_id, notes="面经：一面问了 ReAct")

    names = [n for n, _ in events]
    assert names[-1] == "done" and names.count("delta") > 3
    # 把所有片段拼起来，就是模型输出的完整 JSON
    streamed = "".join(d["text"] for n, d in events if n == "delta")
    assert json.loads(streamed)["summary"].startswith("Agent")

    done = events[-1][1]
    # (必备 strong 100×2 + 加分项 missing 0×1) / 3 = 66.7 → 67
    assert done["report"]["score"] == 67 and done["stale"] is False
    assert fake.max_tokens == MATCH_MAX_TOKENS > 8192  # 输出很长，不能用默认的 8192
    prompt = fake.prompts[0]
    assert (
        "<resume>" in prompt and "LangGraph" in prompt and "<notes>" in prompt and "ReAct" in prompt
    )

    saved = (await alice.get(f"/api/applications/{app_id}/match-report")).json()
    assert saved["id"] == done["id"]

    items = (await alice.get(f"/api/applications/{app_id}/prep-items")).json()
    assert [i["content"] for i in items] == ["动手实现一个最小 RAG", "复习 LangGraph 状态机设计"]
    assert all(i["source"] == "ai" and not i["done"] for i in items)

    async with TestSessionLocal() as s:
        [log] = (await s.execute(select(LLMCallLog))).scalars().all()
    assert log.feature == "match_report" and log.success and log.output_tokens == 400


async def test_reset_event_is_forwarded(alice, use_llm):
    use_llm(FakeStreamLLM(reset=True))
    events = await run_match(alice, await setup_app(alice))
    names = [n for n, _ in events]
    assert "reset" in names and names[-1] == "done"


async def test_llm_failure_mid_stream_sends_error_and_saves_nothing(alice, use_llm):
    use_llm(FakeStreamLLM(error=LLMError("deepseek 请求过于频繁")))
    app_id = await setup_app(alice)
    events = await run_match(alice, app_id)
    name, data = events[-1]
    assert name == "error" and "请求过于频繁" in data["detail"]
    assert (await alice.get(f"/api/applications/{app_id}/match-report")).json() is None
    assert (await alice.get(f"/api/applications/{app_id}/prep-items")).json() == []
    async with TestSessionLocal() as s:
        [log] = (await s.execute(select(LLMCallLog))).scalars().all()
    assert not log.success


async def test_report_becomes_stale_after_resume_changes(alice, use_llm):
    use_llm(FakeStreamLLM())
    app_id = await setup_app(alice)
    await run_match(alice, app_id)
    await alice.put("/api/resume", json={"content_md": RESUME + "\n新增：RAG 实习经历"})
    assert (await alice.get(f"/api/applications/{app_id}/match-report")).json()["stale"] is True


async def test_regenerate_keeps_done_and_manual_items(alice, use_llm):
    use_llm(FakeStreamLLM())
    app_id = await setup_app(alice)
    await run_match(alice, app_id)
    items = (await alice.get(f"/api/applications/{app_id}/prep-items")).json()
    await alice.patch(f"/api/prep-items/{items[0]['id']}", json={"done": True})
    await alice.post(f"/api/applications/{app_id}/prep-items", json={"content": "背熟自我介绍"})

    await run_match(alice, app_id)  # 重新生成

    after = (await alice.get(f"/api/applications/{app_id}/prep-items")).json()
    contents = [i["content"] for i in after]
    assert "背熟自我介绍" in contents  # 手动添加的保留
    assert sum(1 for i in after if i["done"]) == 1  # 已完成的 AI 条目保留
    assert len(after) == 1 + 1 + 2  # 手动 1 + 已完成 1 + 新生成 2（未完成的旧 AI 条目被替换）


# ---------- 中文 / 英文简历 ----------

EN_RESUME = (
    "# Zhang San\nM.S. in CS. Built a multi-agent research assistant with LangGraph and tool use."
)
EN_JD = (
    "Software Engineer, AI Agents. Requirements: strong Python; experience with LLM tool use, "
    "planning and memory; RAG experience is a plus."
)


async def add_app(client, jd: str) -> str:
    body = {"company": "Northstar", "role": "Agent Engineer", "jd_text": jd}
    return (await client.post("/api/applications", json=body)).json()["id"]


async def test_auto_picks_resume_by_jd_language(alice, use_llm):
    fake = use_llm(FakeStreamLLM())
    await alice.put("/api/resume", json={"content_md": RESUME})
    await alice.put("/api/resume?language=en", json={"content_md": EN_RESUME})

    en_done = (await run_match(alice, await add_app(alice, EN_JD)))[-1][1]
    zh_done = (await run_match(alice, await add_app(alice, JD)))[-1][1]

    assert en_done["resume_language"] == "en" and "Zhang San" in fake.prompts[0]
    assert zh_done["resume_language"] == "zh" and "张三" in fake.prompts[1]


async def test_auto_falls_back_to_the_only_resume(alice, use_llm):
    fake = use_llm(FakeStreamLLM())
    await alice.put("/api/resume", json={"content_md": RESUME})  # 只有中文简历
    done = (await run_match(alice, await add_app(alice, EN_JD)))[-1][1]
    assert done["resume_language"] == "zh" and "张三" in fake.prompts[0]


async def test_explicit_language_overrides_auto_and_must_exist(alice, use_llm):
    fake = use_llm(FakeStreamLLM())
    await alice.put("/api/resume", json={"content_md": RESUME})
    app_id = await add_app(alice, EN_JD)

    url = f"/api/applications/{app_id}/match-report"
    resp = await alice.post(url, json={"resume_language": "en"})
    assert resp.status_code == 400 and "英文简历" in resp.json()["detail"]

    await alice.put("/api/resume?language=en", json={"content_md": EN_RESUME})
    done = (await run_match(alice, app_id, resume_language="zh"))[-1][1]
    assert done["resume_language"] == "zh" and "张三" in fake.prompts[0]


async def test_stale_only_tracks_the_resume_that_was_used(alice, use_llm):
    use_llm(FakeStreamLLM())
    await alice.put("/api/resume", json={"content_md": RESUME})
    await alice.put("/api/resume?language=en", json={"content_md": EN_RESUME})
    app_id = await add_app(alice, EN_JD)
    await run_match(alice, app_id)  # 用的是英文简历
    url = f"/api/applications/{app_id}/match-report"

    await alice.put("/api/resume", json={"content_md": RESUME + "\n新增：RAG 实习经历"})
    assert (await alice.get(url)).json()["stale"] is False  # 改中文简历不影响

    await alice.put("/api/resume?language=en", json={"content_md": EN_RESUME + "\nRAG intern."})
    assert (await alice.get(url)).json()["stale"] is True


def test_jd_language_detection():
    from app.models import Application
    from app.services.match import jd_language

    assert jd_language(Application(jd_text=EN_JD)) == "en"
    assert jd_language(Application(jd_text=JD)) == "zh"  # 中文里夹着 Python、RAG 仍是中文
    assert jd_language(Application(jd_text=None, jd_parsed={"skills": ["Python", "RAG"]})) == "en"
    assert jd_language(Application(jd_text=None, jd_parsed={"title": "后端开发"})) == "zh"


# ---------- 备考清单 ----------


async def test_prep_item_crud_and_isolation(alice, user_client):
    app_id = await setup_app(alice)
    item = (
        await alice.post(
            f"/api/applications/{app_id}/prep-items",
            json={"content": "复习 TCP 三次握手", "category": "knowledge", "priority": 1},
        )
    ).json()
    assert item["source"] == "manual" and item["priority"] == 1

    updated = (await alice.patch(f"/api/prep-items/{item['id']}", json={"done": True})).json()
    assert updated["done"] is True

    bob = await user_client("bob@example.com")
    assert (
        await bob.patch(f"/api/prep-items/{item['id']}", json={"done": False})
    ).status_code == 404
    assert (await bob.delete(f"/api/prep-items/{item['id']}")).status_code == 404

    assert (await alice.delete(f"/api/prep-items/{item['id']}")).status_code == 204
    assert (await alice.get(f"/api/applications/{app_id}/prep-items")).json() == []


async def test_prep_item_validation(alice):
    app_id = await setup_app(alice)
    url = f"/api/applications/{app_id}/prep-items"
    assert (await alice.post(url, json={"content": ""})).status_code == 422
    assert (await alice.post(url, json={"content": "x", "priority": 5})).status_code == 422


# ---------- 输出格式的兜底 ----------


def test_analysis_truncates_lists():
    data = ANALYSIS.model_dump()
    data["interview_questions"] = [f"问题 {i}" for i in range(20)]
    data["resume_edits"] = data["resume_edits"] * 12
    parsed = MatchAnalysis.model_validate(data)
    assert len(parsed.interview_questions) == 8 and len(parsed.resume_edits) == 8


def _req(importance: str, level: str) -> RequirementMatch:
    return RequirementMatch(
        requirement="x", importance=importance, level=level, evidence=None, advice="y"
    )


@pytest.mark.parametrize(
    ("reqs", "expected"),
    [
        ([], 0),
        ([("required", "strong")] * 3, 100),
        ([("required", "missing")] * 3, 0),
        ([("required", "partial")], 50),
        # 必备要求权重是加分项的两倍：(100×2 + 0×1) / 3 = 66.7
        ([("required", "strong"), ("preferred", "missing")], 67),
        ([("required", "missing"), ("preferred", "strong")], 33),
        # 四舍五入而不是银行家舍入：(50×1 + 0×1 + 100×2) / 4 = 62.5 → 63
        ([("preferred", "partial"), ("preferred", "missing"), ("required", "strong")], 63),
    ],
)
def test_score_is_computed_by_rule(reqs, expected):
    assert compute_score([_req(i, lv) for i, lv in reqs]) == expected


def test_model_cannot_set_score_and_schema_does_not_ask_for_it():
    data = ANALYSIS.model_dump()
    data["score"] = 99  # 模型自作主张给的分数被忽略
    assert MatchAnalysis.model_validate(data).score == 67
    # 发给模型的 Schema 里没有 score，模型就不会去打分
    assert "score" not in MatchAnalysis.model_json_schema()["properties"]


def test_old_reports_are_rescored_with_current_rule():
    """旧数据：没有 importance、score 是模型给的。读取时都当作必备要求，按规则重新计算。"""
    raw = ANALYSIS.model_dump(mode="json")
    raw["score"] = 90
    for r in raw["requirements"]:
        del r["importance"]
    del raw["resume_edits"]
    loaded = MatchAnalysis.from_stored(raw)
    assert loaded.score == 50 and loaded.resume_edits == []


async def test_resume_edits_are_returned_and_old_reports_still_load(alice, use_llm):
    use_llm(FakeStreamLLM())
    app_id = await setup_app(alice)
    done = (await run_match(alice, app_id))[-1][1]
    [edit] = done["report"]["resume_edits"]
    assert edit["original"].startswith("项目：") and "【待补充" in edit["suggestion"]

    # 模拟加这个字段之前存下的旧分析：读取时不报错，补成空列表
    async with TestSessionLocal() as s:
        report = await s.get(MatchReport, uuid.UUID(done["id"]))
        report.report = {k: v for k, v in report.report.items() if k != "resume_edits"}
        await s.commit()
    saved = (await alice.get(f"/api/applications/{app_id}/match-report")).json()
    assert saved["report"]["resume_edits"] == []
