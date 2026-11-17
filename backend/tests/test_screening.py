"""岗位快速筛选：读取岗位 → 硬条件过滤 → 粗筛 → 补充 JD → 精排 → 加入投递记录。

大模型用假实现代替：按岗位名里的关键词给粗筛分数，按 JD 内容给精排判断，结果可预测。
"""

import json
import re

import pytest

from app.api.deps import optional_llm, require_llm
from app.llm import LLMError, StructuredResult
from app.main import app
from app.schemas.jd import ParsedJD
from app.schemas.screening import ExtractedJob, ExtractedJobs, QuickMatch, Triage, TriageItem

RESUME = "# 张三\n硕士，研究方向 LLM Agent。\n项目：用 LangGraph 搭建多 Agent 论文助手，支持工具调用。\n技能：Python"
PAGE_TEXT = """首页 | 校园招聘 | 社会招聘
Agent 开发工程师  北京  技术  校招
大模型应用工程师  上海  技术  校招
销售经理  北京  销售  校招
后端开发工程师  深圳  技术  校招
数据分析实习生  北京  数据  实习
关于我们 | 联系方式"""


class FakeLLM:
    """按 schema 返回不同的结果。"""

    provider = "fake"
    model = "fake-model"

    def __init__(self, *, fail_rank_for: str | None = None, drop_triage_index: int | None = None):
        self.calls: list[str] = []
        self.fail_rank_for = fail_rank_for
        self.drop_triage_index = drop_triage_index

    async def structured(self, *, system, user, schema, effort="medium", max_tokens=4096):
        self.calls.append(schema.__name__)
        if schema is ExtractedJobs:
            data = ExtractedJobs(jobs=_extract(user))
        elif schema is Triage:
            data = _triage(user, self.drop_triage_index)
        elif schema is QuickMatch:
            if self.fail_rank_for and self.fail_rank_for in user:
                raise LLMError("deepseek 请求过于频繁")
            data = _quick_match(user)
        elif schema is ParsedJD:
            data = ParsedJD(
                company=None, role="Agent 开发工程师", location="北京", job_type="校招",
                salary=None, deadline=None, responsibilities=["开发 Agent"],
                requirements=["熟悉 Python"], bonus=[], tech_stack=["Python"], summary="看重 Agent",
            )  # fmt: skip
        else:
            raise AssertionError(schema)
        return StructuredResult(data, "fake", "fake-model", 100, 50)


def _extract(prompt: str) -> list[ExtractedJob]:
    page = prompt.split("<page>")[1].split("</page>")[0]
    jobs = []
    for line in page.splitlines():
        parts = line.split()
        # 岗位行的格式：“岗位名 地点 类别 招聘类型”；导航栏、页脚等行跳过（模拟模型识别出非岗位）
        if len(parts) >= 4 and parts[-1] in ("校招", "实习", "社招"):
            title = " ".join(parts[:-3])
            loc, cat, jtype = parts[-3:]
            jobs.append(
                ExtractedJob(
                    title=title,
                    location=loc,
                    category=cat,
                    job_type=jtype,
                    url=f"/jobs/{len(jobs)}",
                    snippet=None,
                )
            )
    return jobs


def _triage(prompt: str, drop: int | None) -> Triage:
    block = prompt.split("<jobs>")[1].split("</jobs>")[0]
    items = []
    for line in block.strip().splitlines():
        m = re.match(r"(\d+)\. (.+)", line)
        index, title = int(m.group(1)), m.group(2)
        if index == drop:
            continue
        score = 3 if ("Agent" in title or "大模型" in title) else (0 if "销售" in title else 1)
        items.append(TriageItem(index=index, score=score, reason="测试"))
    return Triage(items=items)


def _quick_match(prompt: str) -> QuickMatch:
    jd = prompt.split("<jd>")[1].split("</jd>")[0]
    strong = "Agent" in jd
    return QuickMatch.model_validate(
        {
            "requirements": [
                {
                    "requirement": "Python",
                    "importance": "required",
                    "level": "strong",
                    "evidence": "技能：Python",
                },
                {
                    "requirement": "Agent 经验",
                    "importance": "required",
                    "level": "strong" if strong else "missing",
                    "evidence": "多 Agent 论文助手" if strong else None,
                },
                {
                    "requirement": "Go 语言",
                    "importance": "preferred",
                    "level": "missing",
                    "evidence": None,
                },
            ],  # fmt: skip
            "strength": "Agent 项目对口" if strong else "Python 基础",
            "gap": "缺少 Go",
        }
    )


@pytest.fixture
def use_llm():
    def _use(fake):
        app.dependency_overrides[require_llm] = lambda: fake
        app.dependency_overrides[optional_llm] = lambda: fake
        return fake

    yield _use
    app.dependency_overrides.pop(require_llm, None)
    app.dependency_overrides.pop(optional_llm, None)


@pytest.fixture
async def alice(user_client):
    c = await user_client("alice@example.com")
    await c.put("/api/resume", json={"content_md": RESUME})
    return c


async def new_batch(client, **body) -> dict:
    payload = {"company": "北辰云", "source_url": "https://jobs.example.com/campus", **body}
    resp = await client.post("/api/screening/batches", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def run_rank(client, batch_id: str) -> list[tuple[str, dict]]:
    events = []
    async with client.stream("POST", f"/api/screening/batches/{batch_id}/rank") as resp:
        assert resp.status_code == 200, await resp.aread()
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


# ---------- 读取岗位 ----------


async def test_extract_from_pasted_text_and_dedupe(alice, use_llm):
    use_llm(FakeLLM())
    batch = await new_batch(alice)
    url = f"/api/screening/batches/{batch['id']}/extract"

    first = (await alice.post(url, json={"text": PAGE_TEXT})).json()
    assert first == {"added": 5, "duplicated": 0, "total": 5}
    again = (await alice.post(url, json={"text": PAGE_TEXT})).json()  # 翻页重复读取
    assert again == {"added": 0, "duplicated": 5, "total": 5}

    detail = (await alice.get(f"/api/screening/batches/{batch['id']}")).json()
    titles = [j["title"] for j in detail["jobs"]]
    assert "Agent 开发工程师" in titles and "关于我们" not in " ".join(titles)
    # 相对链接按来源页面补全成完整地址
    assert all(j["url"].startswith("https://jobs.example.com/jobs/") for j in detail["jobs"])


async def test_add_structured_jobs_dedupes_by_url_or_title(alice):
    batch = await new_batch(alice)
    url = f"/api/screening/batches/{batch['id']}/jobs"
    jobs = [
        {"title": "Agent 开发", "url": "https://x.com/1"},
        {"title": "Agent 开发", "url": "https://x.com/1"},  # 同一链接
        {"title": "后端开发", "location": "北京"},
        {"title": "后端开发", "location": "北京"},  # 没有链接：按岗位名 + 地点
        {"title": "后端开发", "location": "上海"},
    ]
    assert (await alice.post(url, json={"jobs": jobs})).json()["added"] == 3


async def test_batches_are_private(alice, user_client):
    batch = await new_batch(alice)
    bob = await user_client("bob@example.com")
    assert (await bob.get(f"/api/screening/batches/{batch['id']}")).status_code == 404
    jobs_url = f"/api/screening/batches/{batch['id']}/jobs"
    assert (await bob.post(jobs_url, json={"jobs": [{"title": "x"}]})).status_code == 404
    assert (await bob.get("/api/screening/batches")).json() == []


# ---------- 硬条件过滤 + 粗筛 ----------


async def test_screen_filters_then_shortlists_top_n(alice, use_llm):
    fake = use_llm(FakeLLM())
    filters = {"cities": ["北京", "上海"], "job_types": ["校招"], "exclude_keywords": ["实习"]}
    batch = await new_batch(alice, filters=filters, top_n=2)
    await alice.post(f"/api/screening/batches/{batch['id']}/extract", json={"text": PAGE_TEXT})

    result = (await alice.post(f"/api/screening/batches/{batch['id']}/screen")).json()
    jobs = {j["title"]: j for j in result["batch"]["jobs"]}

    assert jobs["后端开发工程师"]["filtered_reason"] == "地点为深圳"
    assert "实习" in jobs["数据分析实习生"]["filtered_reason"]
    assert jobs["销售经理"]["coarse_score"] == 0 and not jobs["销售经理"]["shortlisted"]
    shortlisted = {t for t, j in jobs.items() if j["shortlisted"]}
    assert shortlisted == {"Agent 开发工程师", "大模型应用工程师"}
    # 进入精排、但还没有 JD 的岗位，返回给插件去读详情页
    assert {j["title"] for j in result["needs_jd"]} == shortlisted
    assert result["batch"]["status"] == "screened"
    # 被过滤掉的岗位不发给模型
    assert fake.calls.count("Triage") == 1


async def test_triage_keeps_jobs_the_model_forgot(alice, use_llm):
    use_llm(FakeLLM(drop_triage_index=0))  # 模型漏判了第一个岗位
    batch = await new_batch(alice)
    await alice.post(
        f"/api/screening/batches/{batch['id']}/jobs", json={"jobs": [{"title": "数据开发"}]}
    )
    result = (await alice.post(f"/api/screening/batches/{batch['id']}/screen")).json()
    [job] = result["batch"]["jobs"]
    assert job["coarse_score"] == 2 and job["shortlisted"]  # 宁可多留


async def test_screen_requires_jobs_and_resume(user_client, use_llm):
    use_llm(FakeLLM())
    c = await user_client("carol@example.com")  # 没有简历
    batch = await new_batch(c)
    resp = await c.post(f"/api/screening/batches/{batch['id']}/screen")
    assert resp.status_code == 400 and "岗位" in resp.json()["detail"]
    await c.post(f"/api/screening/batches/{batch['id']}/jobs", json={"jobs": [{"title": "x"}]})
    resp = await c.post(f"/api/screening/batches/{batch['id']}/screen")
    assert resp.status_code == 400 and "简历" in resp.json()["detail"]


# ---------- 精排 ----------


async def screened_batch(client) -> tuple[str, dict[str, dict]]:
    batch = await new_batch(client, top_n=3)
    await client.post(
        f"/api/screening/batches/{batch['id']}/jobs",
        json={
            "jobs": [
                {"title": "Agent 开发工程师"},
                {"title": "大模型应用工程师"},
                {"title": "测试开发"},
                {"title": "销售经理"},
            ]
        },  # fmt: skip
    )
    result = (await client.post(f"/api/screening/batches/{batch['id']}/screen")).json()
    return batch["id"], {j["title"]: j for j in result["batch"]["jobs"]}


async def test_rank_requires_jd(alice, use_llm):
    use_llm(FakeLLM())
    batch_id, _ = await screened_batch(alice)
    resp = await alice.post(f"/api/screening/batches/{batch_id}/rank")
    assert resp.status_code == 400 and "JD" in resp.json()["detail"]


async def test_rank_scores_by_rule_and_sorts(alice, use_llm):
    use_llm(FakeLLM())
    batch_id, jobs = await screened_batch(alice)
    jd = "任职要求：熟悉 Python；有 Agent 开发经验；熟悉 Go 优先。"
    await alice.put(
        f"/api/screening/jobs/{jobs['Agent 开发工程师']['id']}/jd", json={"jd_text": jd}
    )
    await alice.put(
        f"/api/screening/jobs/{jobs['测试开发']['id']}/jd",
        json={"jd_text": "任职要求：熟悉 Python 和自动化测试框架，了解持续集成。"},
    )

    events = await run_rank(alice, batch_id)
    names = [n for n, _ in events]
    assert names[0] == "start" and events[0][1]["total"] == 2
    assert names.count("job") == 2 and names[-1] == "done"

    done = events[-1][1]
    assert done["status"] == "ranked" and done["ranked_jobs"] == 2
    top = done["jobs"][0]
    # (Python strong 100×2 + Agent strong 100×2 + Go missing 0×1) / 5 = 80
    assert top["title"] == "Agent 开发工程师" and top["score"] == 80
    assert top["rank_result"]["strength"] == "Agent 项目对口"
    assert top["rank_result"]["resume_language"] == "zh"
    second = done["jobs"][1]
    assert second["title"] == "测试开发" and second["score"] == 40  # (200 + 0 + 0) / 5
    # 进入精排但没有 JD 的岗位排在已精排的后面
    assert done["jobs"][2]["title"] == "大模型应用工程师" and done["jobs"][2]["score"] is None


async def test_one_failed_rank_does_not_stop_others(alice, use_llm):
    use_llm(FakeLLM(fail_rank_for="测试开发"))
    batch_id, jobs = await screened_batch(alice)
    for title in ("Agent 开发工程师", "测试开发"):
        await alice.put(
            f"/api/screening/jobs/{jobs[title]['id']}/jd",
            json={"jd_text": f"{title}：熟悉 Python，有 Agent 开发经验者优先。"},
        )
    done = (await run_rank(alice, batch_id))[-1][1]
    by_title = {j["title"]: j for j in done["jobs"]}
    assert by_title["Agent 开发工程师"]["score"] == 80
    assert by_title["测试开发"]["score"] is None
    assert "请求过于频繁" in by_title["测试开发"]["rank_error"]


async def test_changing_jd_invalidates_rank(alice, use_llm):
    use_llm(FakeLLM())
    batch_id, jobs = await screened_batch(alice)
    job_url = f"/api/screening/jobs/{jobs['Agent 开发工程师']['id']}/jd"
    await alice.put(job_url, json={"jd_text": "熟悉 Python，有 Agent 开发经验。"})
    await run_rank(alice, batch_id)
    job = (await alice.put(job_url, json={"jd_text": "熟悉 Java 和 Spring Boot 开发。"})).json()
    assert job["score"] is None and job["rank_result"] is None


# ---------- 加入投递记录 ----------


async def test_import_creates_wishlist_application_once(alice, use_llm):
    use_llm(FakeLLM())
    batch_id, jobs = await screened_batch(alice)
    job_id = jobs["Agent 开发工程师"]["id"]
    await alice.put(
        f"/api/screening/jobs/{job_id}/jd", json={"jd_text": "熟悉 Python，有 Agent 经验。"}
    )
    await run_rank(alice, batch_id)

    first = await alice.post(f"/api/screening/jobs/{job_id}/import")
    assert first.status_code == 201
    app_id = first.json()["application_id"]
    again = (await alice.post(f"/api/screening/jobs/{job_id}/import")).json()
    assert again["application_id"] == app_id  # 重复点击不会重复创建

    detail = (await alice.get(f"/api/applications/{app_id}")).json()
    assert detail["stage"] == "wishlist" and detail["company"] == "北辰云"
    assert detail["role"] == "Agent 开发工程师" and "Agent" in detail["jd_text"]
    assert detail["jd_parsed"]["summary"] == "看重 Agent"  # 顺便解析了 JD
    assert "匹配度 80" in detail["notes"]
    assert len((await alice.get("/api/applications")).json()) == 1

    batch = (await alice.get(f"/api/screening/batches/{batch_id}")).json()
    assert next(j for j in batch["jobs"] if j["id"] == job_id)["application_id"] == app_id


async def test_import_works_without_llm(alice):
    batch = await new_batch(alice)
    await alice.post(
        f"/api/screening/batches/{batch['id']}/jobs",
        json={"jobs": [{"title": "Agent 开发", "snippet": "负责 Agent 应用开发"}]},
    )
    [job] = (await alice.get(f"/api/screening/batches/{batch['id']}")).json()["jobs"]
    app.dependency_overrides[optional_llm] = lambda: None  # 没配 API Key
    try:
        resp = await alice.post(f"/api/screening/jobs/{job['id']}/import")
    finally:
        app.dependency_overrides.pop(optional_llm, None)
    assert resp.status_code == 201
    detail = (await alice.get(f"/api/applications/{resp.json()['application_id']}")).json()
    assert detail["jd_text"] == "负责 Agent 应用开发" and detail["jd_parsed"] is None


async def test_delete_batch(alice):
    batch = await new_batch(alice)
    assert (await alice.delete(f"/api/screening/batches/{batch['id']}")).status_code == 204
    assert (await alice.get(f"/api/screening/batches/{batch['id']}")).status_code == 404
