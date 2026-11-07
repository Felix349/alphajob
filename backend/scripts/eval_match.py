"""岗位匹配分析评估：真实调用大模型，用代码自动检查输出质量（不让模型给模型打分）。

两类用例：
- evals/match/cases.jsonl：虚构的简历 + JD，带针对性的期望（分数区间、必备 / 加分项、缺失项）
- --real：本地的真实 JD（evals/jd_parse/raw/*.txt）× 数据库里你的简历，只做通用检查。
  真实数据不进仓库，结果也只存在本地

用法：
  uv run python scripts/eval_match.py                      # 只跑虚构用例
  uv run python scripts/eval_match.py --real --limit 10    # 再加 10 条真实 JD
  uv run python scripts/eval_match.py --only zh-agent-fit --repeat 3   # 看分数是否稳定
"""

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.llm import LLMError, LLMNotConfigured, StreamDone  # noqa: E402
from app.llm.factory import build_llm_client  # noqa: E402
from app.models import Application, Resume, User  # noqa: E402
from app.prompts import match as match_prompt  # noqa: E402
from app.schemas.match import MatchAnalysis  # noqa: E402
from app.services.match import MATCH_MAX_TOKENS, jd_language  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "evals" / "match"
RAW_JD_DIR = ROOT / "evals" / "jd_parse" / "raw"
CONCURRENCY = 4

# 和 schemas/match.py 字段描述里写的条数一致：超出说明模型没按要求来
COUNT_RANGES = {
    "highlights": (2, 5),
    "requirements": (5, 8),
    "prep_items": (5, 10),
    "interview_questions": (3, 8),
    "resume_edits": (3, 6),
}
# 输出 token 的预算：超过就算不合格。上限（MATCH_MAX_TOKENS）只是防截断的保险，
# 真正要控制的是长度本身：输出越长，用户等得越久、花费越多
TOKEN_BUDGET = 10000
# 启发式检查：会有误报（如“工具调用”写成 Tool Use 也会被标出），标出的条目需要人工看
REVIEW_CHECKS = {"no_new_terms", "no_new_numbers"}

_PLACEHOLDER = re.compile(r"【[^】]*】")
_CJK = re.compile(r"[一-鿿]")
_LATIN = re.compile(r"[A-Za-z]")
# 独立的数字：BM25、top-5、Qwen2.5 这类“名字里的数字”不算
# 小数整体匹配（3.2s 取出 3.2，不会拆成 3 和 2）；单位紧跟在后面没关系
_NUMBER = re.compile(r"(?<![A-Za-z0-9@\-_.])\d+(?:\.\d+)?")
# 英文单词（含 C++、Node.js 这类写法），再由 tech_terms 挑出“像技术名词”的
# 不含连字符：MySQL-to-PostgreSQL 拆成 MySQL、to、PostgreSQL 分别判断
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.]*[A-Za-z0-9+#]|[A-Za-z]")
# 拔高职责、替求职者表态的说法：简历原文里没有，改写里就不该出现
INFLATION_WORDS = [
    "主导", "独立", "全流程", "从 0 到 1", "从0到1", "牵头", "精通", "正在学习", "系统学习",
    "led ", "spearheaded", "owned ", "single-handedly", "end-to-end",
]  # fmt: skip


# ---------- 检查项 ----------


def norm(s: str) -> str:
    """比较原文时忽略空白、Markdown 符号和首尾标点（模型引用时常常省略句号）。"""
    s = re.sub(r"[\s*#>`_]|^[-•·]", "", s)
    return s.strip("。.，,；;：:").lower()


def cjk_ratio(text: str) -> float:
    cjk, latin = len(_CJK.findall(text)), len(_LATIN.findall(text))
    return cjk / (cjk + latin) if cjk + latin else 0.0


def _jd_proper_nouns(jd: str) -> set[str]:
    """JD 里“句中”出现的首字母大写词（Java、Kafka、Spring）：大概率是技术名。
    句首、条目开头的大写词（Strong、Experience）不算，它们只是英文句子的开头。"""
    nouns = set()
    for m in _WORD.finditer(jd):
        w = m.group()
        before = jd[: m.start()].rstrip(" ")
        at_start = not before or before[-1] in ".!?\n-•*:"
        if len(w) >= 2 and w[0].isupper() and not at_start:
            nouns.add(w)
    return nouns


def tech_terms(text: str, jd: str) -> list[str]:
    """挑出像技术名词的英文词：
    - 含大写字母（首字母以外）、数字或 +#. 符号，或全大写：LangGraph、BM25、C++、SQL
    - JD 句中出现过的首字母大写词：Java、Kafka
    全小写的普通单词（planning、memory）和一般的英文句首单词（Built、Designed）不算。"""
    jd_nouns = _jd_proper_nouns(jd)
    return [
        w
        for w in _WORD.findall(text)
        if re.search(r"[A-Z0-9+#.]", w[1:]) or (len(w) >= 2 and w.isupper()) or w in jd_nouns
    ]


def find_requirement(a: MatchAnalysis, keyword: str):
    k = keyword.lower()
    return next((r for r in a.requirements if k in r.requirement.lower()), None)


def generic_checks(a: MatchAnalysis, resume: str, jd: str, language: str, out_tokens: int) -> dict:
    """对所有用例都做的检查。返回 {检查项: (是否通过, 失败时的说明)}。"""
    r: dict[str, tuple[bool, str]] = {}

    bad_counts = [
        f"{k}={len(getattr(a, k))}（应为 {lo}–{hi}）"
        for k, (lo, hi) in COUNT_RANGES.items()
        if not lo <= len(getattr(a, k)) <= hi
    ]
    r["counts"] = (not bad_counts, "；".join(bad_counts))

    # 有依据才能判 strong / partial；判 missing 就不该有依据
    bad_evidence = [
        f"[{x.level}] {x.requirement}"
        for x in a.requirements
        if (x.level == "missing") != (x.evidence is None)
    ]
    r["evidence_rule"] = (not bad_evidence, "；".join(bad_evidence))

    # 修改建议引用的原句，必须能在简历里原样找到
    resume_norm = norm(resume)
    not_found = [
        e.original for e in a.resume_edits if e.original and norm(e.original) not in resume_norm
    ]
    r["original_verbatim"] = (not not_found, " | ".join(x[:60] for x in not_found))

    # 改写里出现的数字必须来自简历；需要用户补充的数字应该放进【待补充】
    # 注意：由简历数字算出来的（如 3.2 秒 → 1.4 秒写成“-56%”）也会被标出来，需要人工确认
    resume_numbers = set(_NUMBER.findall(resume))
    new_numbers = []
    for e in a.resume_edits:
        for n in _NUMBER.findall(_PLACEHOLDER.sub("", e.suggestion)):
            if n not in resume_numbers:
                new_numbers.append(f"{n}（{e.section[:20]}）")
    r["no_new_numbers"] = (not new_numbers, "、".join(new_numbers))

    # 改写里不该冒出简历没提过的技术名词。两种都算编造：
    # - 凭空补的细节：简历只写“混合检索”，改写成“BM25 + 向量检索”
    # - 照着 JD 补的技能：电子信息专业的简历里加上“Java、Spring Boot（学习中）”
    # 用“是否为简历原文的子串”判断，所以简历写了 MySQL，改写里出现 SQL 不算新词
    resume_lower = resume.lower()
    new_terms: list[str] = []
    for e in a.resume_edits:
        for t in tech_terms(_PLACEHOLDER.sub("", e.suggestion), jd):
            if t.lower() not in resume_lower and t not in new_terms:
                new_terms.append(t)
    r["no_new_terms"] = (not new_terms, "、".join(new_terms[:12]))

    inflated = [
        f"“{w.strip()}”（{e.section[:20]}）"
        for e in a.resume_edits
        for w in INFLATION_WORDS
        if w in _PLACEHOLDER.sub("", e.suggestion).lower() and w not in resume_lower
    ]
    r["no_inflation"] = (not inflated, "、".join(inflated))

    # 英文简历的改写应该是英文：去掉【待补充】（它是中文）后基本不该有汉字。
    # 中文简历不检查：技能栏这类内容本来就几乎全是英文技术名词
    if language == "en":
        wrong_lang = [
            e.suggestion[:40]
            for e in a.resume_edits
            if cjk_ratio(_PLACEHOLDER.sub("", e.suggestion)) > 0.1
        ]
        r["suggestion_language"] = (not wrong_lang, " | ".join(wrong_lang))

    r["token_budget"] = (
        out_tokens <= TOKEN_BUDGET,
        f"输出 {out_tokens} tokens，预算 {TOKEN_BUDGET}（上限 {MATCH_MAX_TOKENS}）",
    )
    return r


def case_checks(a: MatchAnalysis, exp: dict) -> dict:
    """用例里写了才检查的项。"""
    r: dict[str, tuple[bool, str]] = {}
    if "score_range" in exp:
        lo, hi = exp["score_range"]
        r["score_range"] = (lo <= a.score <= hi, f"得分 {a.score}，期望 {lo}–{hi}")

    def by_keyword(name: str, keywords: list[str], ok) -> None:
        problems = []
        for k in keywords:
            req = find_requirement(a, k)
            if req is None:
                problems.append(f"没有列出含“{k}”的要求")
            elif not ok(req):
                problems.append(f"{k}：{req.importance} / {req.level}")
        r[name] = (not problems, "；".join(problems))

    if "required_contains" in exp:
        by_keyword(
            "importance_required", exp["required_contains"], lambda x: x.importance == "required"
        )
    if "preferred_contains" in exp:
        by_keyword(
            "importance_preferred", exp["preferred_contains"], lambda x: x.importance == "preferred"
        )
    if "missing_contains" in exp:  # 简历里确实没有的：不能判成有（防编造）
        by_keyword("missing_detected", exp["missing_contains"], lambda x: x.level == "missing")
    if "not_missing_contains" in exp:  # 简历里明明有的：不能判成缺失
        by_keyword("present_detected", exp["not_missing_contains"], lambda x: x.level != "missing")
    return r


# ---------- 用例 ----------


def load_cases(only: set[str] | None) -> list[dict]:
    cases = []
    for name in ("cases.jsonl", "cases.local.jsonl"):
        path = EVAL_DIR / name
        if path.exists():
            cases += [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
    return [c for c in cases if not only or c["id"] in only]


async def load_real_cases(email: str | None, limit: int | None) -> list[dict]:
    """真实 JD × 数据库里的简历：按 JD 语言选简历，和线上的自动选择规则一致。"""
    async with SessionLocal() as db:
        stmt = select(Resume).join(User, Resume.user_id == User.id)
        if email:
            stmt = stmt.where(User.email == email)
        resumes = (await db.execute(stmt)).scalars().all()
    if not resumes:
        sys.exit("数据库里没有简历：请先在“我的简历”页面上传，或用 --email 指定用户。")
    user_ids = {r.user_id for r in resumes}
    if len(user_ids) > 1:
        sys.exit("数据库里有多个用户的简历，请用 --email 指定用哪个用户的简历。")
    by_lang = {r.language: r for r in resumes}

    files = sorted(p for p in RAW_JD_DIR.glob("*.txt") if not p.stem.startswith("把真实JD"))
    cases = []
    for p in files[:limit]:
        company, _, role = p.stem.partition("-")
        # 标题作为第一行放进正文：和 JD 解析评估的约定一致
        jd_text = f"{p.stem}\n{p.read_text(encoding='utf-8')}"
        app = Application(company=company, role=role or p.stem, jd_text=jd_text)
        lang = jd_language(app)
        resume = by_lang.get(lang) or next(iter(by_lang.values()))
        cases.append(
            {
                "id": f"real:{p.stem}"[:40],
                "company": company,
                "role": role or p.stem,
                "jd_text": jd_text,
                "resume_md": resume.content_md,
                "resume_language": resume.language,
                "expected": {},
            }
        )
    return cases


# ---------- 运行 ----------


async def run_case(llm, case: dict, sem: asyncio.Semaphore) -> dict:
    app = Application(company=case["company"], role=case["role"], jd_text=case["jd_text"])
    async with sem:
        start = time.perf_counter()
        try:
            result = None
            async for ev in llm.stream_structured(
                system=match_prompt.SYSTEM,
                user=match_prompt.build_prompt(app, case["resume_md"], case.get("notes")),
                schema=MatchAnalysis,
                effort="medium",
                max_tokens=MATCH_MAX_TOKENS,
            ):
                if isinstance(ev, StreamDone):
                    result = ev.result
        except LLMError as exc:
            return {"id": case["id"], "error": str(exc), "checks": {}}
    a: MatchAnalysis = result.data
    checks = {
        **generic_checks(
            a, case["resume_md"], case["jd_text"], case["resume_language"], result.output_tokens
        ),
        **case_checks(a, case.get("expected", {})),
    }
    return {
        "id": case["id"],
        "latency_ms": int((time.perf_counter() - start) * 1000),
        "tokens": [result.input_tokens, result.output_tokens],
        "score": a.score,
        "checks": {k: {"ok": ok, "detail": d} for k, (ok, d) in checks.items()},
        "output": a.model_dump(mode="json"),
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只跑这些用例 id，逗号分隔")
    ap.add_argument("--repeat", type=int, default=1, help="每条用例重复次数（看分数是否稳定）")
    ap.add_argument("--real", action="store_true", help="加上本地真实 JD × 数据库里的简历")
    ap.add_argument("--limit", type=int, help="--real 时最多取多少条 JD")
    ap.add_argument("--email", help="--real 时用哪个用户的简历")
    args = ap.parse_args()

    try:
        llm = build_llm_client(get_settings())
    except LLMNotConfigured as exc:
        sys.exit(f"无法评估：{exc}。请先在仓库根目录的 .env 中填写对应的 API Key。")

    cases = load_cases(set(args.only.split(",")) if args.only else None)
    if args.real:
        cases += await load_real_cases(args.email, args.limit)
    print(f"服务商 {llm.provider} · 模型 {llm.model} · {len(cases)} 条用例 × {args.repeat} 次\n")

    sem = asyncio.Semaphore(CONCURRENCY)
    results = await asyncio.gather(
        *(run_case(llm, c, sem) for c in cases for _ in range(args.repeat))
    )

    stats: dict[str, list[bool]] = {}
    scores: dict[str, list[int]] = {}
    for r in results:
        if "error" in r:
            print(f"✗ {r['id']:<40} 调用失败：{r['error']}")
            continue
        scores.setdefault(r["id"], []).append(r["score"])
        failed = {k: c["detail"] for k, c in r["checks"].items() if not c["ok"]}
        for k, c in r["checks"].items():
            stats.setdefault(k, []).append(c["ok"])
        hard_failed = [k for k in failed if k not in REVIEW_CHECKS]
        mark = "✗" if hard_failed else ("?" if failed else "✓")
        secs = r["latency_ms"] / 1000
        chars = len(json.dumps(r["output"], ensure_ascii=False))
        print(
            f"{mark} {r['id']:<40} {r['score']:>3} 分 {r['tokens'][1]:>6} tok "
            f"{chars:>6} 字 {secs:>5.0f} s"
        )
        for k, detail in failed.items():
            print(f"    {'待复核 ' if k in REVIEW_CHECKS else ''}{k}: {detail}")

    print("\n按检查项统计（标 * 的是启发式检查，标出的条目需要人工复核，不计入通过率）：")
    for k, v in sorted(stats.items()):
        star = "*" if k in REVIEW_CHECKS else " "
        print(f" {star}{k:<22} {sum(v)}/{len(v)}  {sum(v) / len(v):.0%}")
    total = [ok for k, v in stats.items() if k not in REVIEW_CHECKS for ok in v]
    if total:
        print(f"\n整体通过率：{sum(total)}/{len(total)} = {sum(total) / len(total):.1%}")
    unstable = {k: v for k, v in scores.items() if len(v) > 1}
    if unstable:
        print("\n分数稳定性（重复运行）：")
        for k, v in unstable.items():
            print(f"  {k:<40} {v}  极差 {max(v) - min(v)}")
    errors = sum(1 for r in results if "error" in r)
    if errors:
        print(f"调用失败：{errors} 次")
    ok = [r for r in results if "error" not in r]
    if ok:
        outs = sorted(r["tokens"][1] for r in ok)
        avg_secs = sum(r["latency_ms"] for r in ok) / len(ok) / 1000
        print(
            f"输出 token：中位数 {outs[len(outs) // 2]}，最大 {outs[-1]}"
            f"（上限 {MATCH_MAX_TOKENS}）；平均耗时 {avg_secs:.0f} s"
        )

    out_dir = EVAL_DIR / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{datetime.now():%Y%m%d-%H%M%S}-{llm.provider}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n详细结果：{out}")


if __name__ == "__main__":
    asyncio.run(main())
