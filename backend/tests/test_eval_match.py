"""匹配分析评估脚本里的检查项本身也要测：检查写错了，评估结果就没有意义。

只测纯函数，不调用大模型。
"""

import importlib.util
from pathlib import Path

import pytest

from tests.test_match import ANALYSIS

_spec = importlib.util.spec_from_file_location(
    "eval_match", Path(__file__).resolve().parents[1] / "scripts" / "eval_match.py"
)
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)

RESUME = (
    "# 李明\n- 用 LangGraph 搭建多 Agent 系统，支持工具调用与长期记忆\n"
    "- 基于 LlamaIndex 和 Milvus 构建问答，支持混合检索与重排序\n"
    "- 首屏加载时间从 3.2 秒降到 1.4 秒\n技能：Python、MySQL、Docker"
)
JD = "要求：熟悉 Python、Java；熟悉 Agent 的 Planning、Tool Use；有 Kafka 经验优先"


def analysis_with_edit(suggestion: str, original: str | None = None):
    data = ANALYSIS.model_dump()
    data["resume_edits"] = [
        {"section": "项目", "original": original, "suggestion": suggestion, "reason": "r"}
    ]
    return ev.MatchAnalysis.model_validate(data)


def check(suggestion: str, original: str | None = None, language: str = "zh") -> dict:
    a = analysis_with_edit(suggestion, original)
    return {k: ok for k, (ok, _) in ev.generic_checks(a, RESUME, JD, language, 100).items()}


@pytest.mark.parametrize(
    ("suggestion", "ok"),
    [
        ("基于 LangGraph 与 Milvus 实现多 Agent 系统", True),
        ("实现规划（planning）与工具调用（tool calling）", True),  # 全小写的翻译不算新技术
        ("用 SQL 优化查询", True),  # 简历写了 MySQL
        ("实现 BM25 + 向量混合检索", False),  # 凭空补的技术细节
        ("后端学习方向：Java、Spring Boot", False),  # 照着 JD 补的技能
        ("Built the service. Designed the cache layer", True),  # 句首大写的普通单词不算
        ("Built REST APIs", False),  # 简历里没有 REST
    ],
)
def test_new_terms(suggestion, ok):
    assert check(suggestion)["no_new_terms"] is ok


@pytest.mark.parametrize(
    ("suggestion", "ok"),
    [
        ("首屏加载时间从 3.2s 降到 1.4s", True),  # 小数不会被拆开
        ("采用 BM25 和 top-5 召回", True),  # 名字里的数字不算
        ("处理【待补充：论文数量】篇论文", True),  # 占位里的不算
        ("处理 1200 篇论文", False),
    ],
)
def test_new_numbers(suggestion, ok):
    assert check(suggestion)["no_new_numbers"] is ok


def test_original_must_be_verbatim_ignoring_markdown_and_trailing_punctuation():
    assert check("x", original="- 用 LangGraph 搭建多 Agent 系统，支持工具调用与长期记忆。")[
        "original_verbatim"
    ]
    assert not check("x", original="用 LangGraph 搭建了一个多 Agent 论文助手")["original_verbatim"]


def test_inflation_words_only_count_when_resume_does_not_have_them():
    assert not check("独立完成从选型到部署的全流程")["no_inflation"]
    assert check("基于 LangGraph 搭建多 Agent 系统")["no_inflation"]


def test_english_suggestions_must_be_english():
    assert check("Built a multi-agent system with LangGraph", language="en")["suggestion_language"]
    assert not check("用 LangGraph 搭建多 Agent 系统", language="en")["suggestion_language"]
    # 中文简历不检查语言：技能栏本来就几乎都是英文
    assert "suggestion_language" not in check("Python、MySQL、Docker")


def test_case_checks_find_requirements_by_keyword():
    # ANALYSIS：“理解 Agent 机制” required/strong；“RAG 经验” preferred/missing
    a = ANALYSIS
    r = ev.case_checks(
        a,
        {
            "score_range": [60, 70],
            "preferred_contains": ["RAG"],
            "missing_contains": ["RAG"],
            "not_missing_contains": ["Agent"],
        },
    )
    assert all(ok for ok, _ in r.values()), r
    r = ev.case_checks(a, {"required_contains": ["RAG", "Kubernetes"]})
    ok, detail = r["importance_required"]
    assert not ok and "preferred" in detail and "没有列出" in detail
