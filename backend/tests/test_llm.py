"""大模型相关测试：全部使用假的模型实现，不发真实请求、不花钱、结果稳定。

真实模型的解析效果用 scripts/ 下的评估脚本单独评估，不放进 CI。
"""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from app.api.applications import require_llm
from app.core.config import Settings
from app.llm import LLMError, LLMNotConfigured, StructuredResult
from app.llm.anthropic_client import AnthropicClient
from app.llm.factory import build_llm_client
from app.llm.openai_compatible import OpenAICompatibleClient
from app.main import app
from app.models import LLMCallLog
from app.schemas.jd import ParsedJD
from tests.conftest import TestSessionLocal

JD_TEXT = (
    "【字节跳动】后端开发工程师-2027届校招，base 北京。"
    "职责：负责抖音推荐系统后端开发。要求：熟悉 Go/Java，了解 Kafka、Redis。"
)

PARSED = ParsedJD(
    company="字节跳动",
    role="后端开发工程师（2027 届校招）",
    location="北京",
    job_type="校招",
    salary=None,
    deadline=None,
    responsibilities=["抖音推荐系统后端开发"],
    requirements=["熟悉 Go 或 Java"],
    bonus=[],
    tech_stack=["Go", "Java", "Kafka", "Redis"],
    summary="看重后端基础和高并发经验",
)


class FakeLLM:
    provider = "fake"
    model = "fake-model"

    def __init__(self, result=None, error: Exception | None = None):
        self.result, self.error, self.calls = result, error, []

    async def structured(self, *, system, user, schema, effort="medium", max_tokens=4096):
        self.calls.append({"system": system, "user": user, "schema": schema, "effort": effort})
        if self.error:
            raise self.error
        return StructuredResult(
            data=self.result, provider=self.provider, model=self.model,
            input_tokens=120, output_tokens=80,
        )  # fmt: skip


@pytest.fixture
def use_llm():
    def _use(fake):
        app.dependency_overrides[require_llm] = lambda: fake
        return fake

    yield _use
    app.dependency_overrides.pop(require_llm, None)


async def _logs() -> list[LLMCallLog]:
    async with TestSessionLocal() as s:
        return list((await s.execute(select(LLMCallLog))).scalars())


# ---------- /parse-jd 接口 ----------


async def test_parse_jd_returns_structured_result_and_logs(user_client, use_llm):
    client = await user_client()
    fake = use_llm(FakeLLM(result=PARSED))
    resp = await client.post("/api/applications/parse-jd", json={"jd_text": JD_TEXT})
    assert resp.status_code == 200, resp.text
    assert resp.json()["tech_stack"] == ["Go", "Java", "Kafka", "Redis"]

    call = fake.calls[0]
    assert call["schema"] is ParsedJD and call["effort"] == "low"
    assert "<jd>" in call["user"] and JD_TEXT in call["user"]  # 原文被标签包裹

    [log] = await _logs()
    assert log.feature == "parse_jd" and log.success
    assert (log.input_tokens, log.output_tokens) == (120, 80)


async def test_parse_jd_llm_failure_returns_502_and_logs_error(user_client, use_llm):
    client = await user_client()
    use_llm(FakeLLM(error=LLMError("deepseek 请求过于频繁")))
    resp = await client.post("/api/applications/parse-jd", json={"jd_text": JD_TEXT})
    assert resp.status_code == 502
    assert "请求过于频繁" in resp.json()["detail"]
    [log] = await _logs()
    assert not log.success and "频繁" in log.error


async def test_parse_jd_validates_input_and_login(client, user_client, use_llm):
    use_llm(FakeLLM(result=PARSED))
    payload = {"jd_text": JD_TEXT}
    assert (await client.post("/api/applications/parse-jd", json=payload)).status_code == 401
    logged_in = await user_client()
    short = {"jd_text": "太短"}
    assert (await logged_in.post("/api/applications/parse-jd", json=short)).status_code == 422


# ---------- 根据配置选择服务商 ----------


def _settings(**kw) -> Settings:
    base = {"jwt_secret": "x" * 32, "deepseek_api_key": "", "anthropic_api_key": ""}
    return Settings(_env_file=None, **{**base, **kw})


def test_factory_requires_api_key():
    with pytest.raises(LLMNotConfigured):
        build_llm_client(_settings(llm_provider="deepseek"))
    with pytest.raises(LLMNotConfigured):
        build_llm_client(_settings(llm_provider="anthropic"))
    with pytest.raises(LLMNotConfigured):  # OpenAI 必须显式配置模型名
        build_llm_client(_settings(llm_provider="openai", openai_api_key="k"))


def test_factory_picks_adapter():
    ds = build_llm_client(_settings(llm_provider="deepseek", deepseek_api_key="k"))
    assert isinstance(ds, OpenAICompatibleClient) and ds.model == "deepseek-chat"
    claude = build_llm_client(_settings(llm_provider="anthropic", anthropic_api_key="k"))
    assert isinstance(claude, AnthropicClient) and claude.model == "claude-opus-5-5"


# ---------- OpenAI 兼容适配器：输出不合格时把错误反馈给模型重试 ----------


class Point(BaseModel):
    x: int
    y: int


def _completion(content: str, finish_reason: str = "stop"):
    return SimpleNamespace(
        model="deepseek-chat",
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        choices=[
            SimpleNamespace(finish_reason=finish_reason, message=SimpleNamespace(content=content))
        ],
    )


def _client_with(responses: list) -> tuple[OpenAICompatibleClient, list]:
    c = OpenAICompatibleClient(provider="deepseek", api_key="k", base_url=None, model="m")
    sent: list = []

    async def create(**kwargs):
        sent.append(kwargs["messages"])
        return responses[len(sent) - 1]

    c._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return c, sent


async def test_openai_compatible_repairs_invalid_json():
    c, sent = _client_with([_completion('{"x": 1}'), _completion('{"x": 1, "y": 2}')])
    result = await c.structured(system="s", user="u", schema=Point)
    assert result.data == Point(x=1, y=2)
    assert (result.input_tokens, result.output_tokens) == (20, 10)  # 两次调用的用量累加
    # 第二次请求带上了模型的错误输出和校验错误
    assert sent[1][-2] == {"role": "assistant", "content": '{"x": 1}'}
    assert "y" in sent[1][-1]["content"]


async def test_openai_compatible_gives_up_after_retries():
    c, _ = _client_with([_completion("not json")] * 3)
    with pytest.raises(LLMError, match="不符合格式"):
        await c.structured(system="s", user="u", schema=Point)


async def test_openai_compatible_reports_truncation():
    c, _ = _client_with([_completion('{"x": 1', finish_reason="length")])
    with pytest.raises(LLMError, match="截断"):
        await c.structured(system="s", user="u", schema=Point)


def test_jd_prompt_includes_today_for_date_inference():
    from datetime import date

    from app.prompts import jd_parse

    prompt = jd_parse.build_prompt("某 JD", today=date(2026, 11, 4))
    assert "今天是 2026-11-04" in prompt
    assert "<jd>\n某 JD\n</jd>" in prompt
