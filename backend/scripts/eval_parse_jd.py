"""JD 解析评估：用固定用例真实调用大模型，按字段统计准确率。

用法：
  uv run python scripts/eval_parse_jd.py
  uv run python scripts/eval_parse_jd.py --only english,no-company
  uv run python scripts/eval_parse_jd.py --repeat 3     # 每条跑 3 次，看结果是否稳定
"""

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.llm import LLMError, LLMNotConfigured  # noqa: E402
from app.llm.factory import build_llm_client  # noqa: E402
from app.prompts import jd_parse  # noqa: E402
from app.schemas.jd import ParsedJD  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parents[1] / "evals" / "jd_parse"
CONCURRENCY = 4


def norm(s: str | None) -> str:
    """比较前统一格式：小写、去掉空白和常见标点。"""
    return re.sub(r"[\s·\-—_()（）【】\[\]|]", "", (s or "").lower())


# 同一技术的不同写法
ALIASES = {"golang": "go", "k8s": "kubernetes", "torch": "pytorch", "py": "python"}


def tech_tokens(items: list[str]) -> list[str]:
    """把 “C/C++”“Python、Go” 这类合写的条目拆开，并统一别名。"""
    tokens = []
    for item in items:
        for part in re.split(r"[/、,，;；]| or |或", item):
            t = ALIASES.get(norm(part), norm(part))
            if t:
                tokens.append(t)
    return tokens


def has_tech(tokens: list[str], want: str) -> bool:
    w = ALIASES.get(norm(want), norm(want))
    # 完全相等；或较长的名字被包含（如 “Doris” 匹配 “Apache Doris”）。
    # 短名字不做包含匹配，避免 “C” 误命中。
    return any(t == w or (len(w) >= 4 and w in t) for t in tokens)


def company_ok(got: str | None, expected) -> bool:
    """expected 可以是一个值，也可以是“几种都算对”的列表（可包含 null）。"""
    options = expected if isinstance(expected, list) else [expected]
    return any(
        (got is None) if opt is None else (got is not None and norm(opt) in norm(got))
        for opt in options
    )


def check(parsed: ParsedJD, exp: dict) -> dict[str, bool]:
    """返回每个检查项是否通过。只检查用例里写了的字段。"""
    r: dict[str, bool] = {}
    if "company" in exp:
        r["company"] = company_ok(parsed.company, exp["company"])
    if "role_contains" in exp:
        r["role"] = any(norm(k) in norm(parsed.role) for k in exp["role_contains"])
    if "location_contains" in exp:
        loc = norm(parsed.location)
        # 用例里中英文写法并列时（如 Singapore / 新加坡），命中一个即可
        keys = exp["location_contains"]
        r["location"] = (
            any(norm(k) in loc for k in keys)
            if len(keys) == 2 and any(k.isascii() for k in keys)
            else all(norm(k) in loc for k in keys)
        )
    if "job_type" in exp:
        r["job_type"] = parsed.job_type == exp["job_type"]
    if "deadline" in exp:
        got = parsed.deadline.isoformat() if parsed.deadline else None
        r["deadline"] = got == exp["deadline"]
    tokens = tech_tokens(parsed.tech_stack)
    if exp.get("tech_stack_must"):
        r["tech_stack"] = all(has_tech(tokens, t) for t in exp["tech_stack_must"])
    if "tech_stack_must_not" in exp:
        stack = [norm(t) for t in parsed.tech_stack]
        r["no_soft_skills"] = not any(
            norm(bad) in t for bad in exp["tech_stack_must_not"] for t in stack
        )
    if "has_bonus" in exp:
        r["bonus"] = bool(parsed.bonus) == exp["has_bonus"]
    if "summary_must_not_contain" in exp:
        r["injection"] = not any(w in parsed.summary for w in exp["summary_must_not_contain"])
    r["non_empty"] = bool(parsed.requirements) and bool(parsed.summary)
    if "company_must_not" in exp:
        r["no_wrong_company"] = not any(
            norm(bad) in norm(parsed.company) for bad in exp["company_must_not"]
        )
    return r


def load_cases(only: set[str] | None) -> list[dict]:
    cases = []
    for name in ("cases.jsonl", "cases.local.jsonl"):
        path = EVAL_DIR / name
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    cases.append(json.loads(line))
    return [c for c in cases if not only or c["id"] in only]


async def run_case(llm, case: dict, sem: asyncio.Semaphore) -> dict:
    async with sem:
        start = time.perf_counter()
        try:
            res = await llm.structured(
                system=jd_parse.SYSTEM,
                user=jd_parse.build_prompt(case["jd_text"], date.fromisoformat(case["today"])),
                schema=ParsedJD,
                effort="low",
            )
        except LLMError as exc:
            return {"id": case["id"], "error": str(exc), "checks": {}}
        return {
            "id": case["id"],
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "tokens": [res.input_tokens, res.output_tokens],
            "checks": check(res.data, case["expected"]),
            "output": res.data.model_dump(mode="json"),
        }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只跑这些用例 id，逗号分隔")
    ap.add_argument("--repeat", type=int, default=1, help="每条用例重复次数")
    args = ap.parse_args()

    settings = get_settings()
    try:
        llm = build_llm_client(settings)
    except LLMNotConfigured as exc:
        sys.exit(f"无法评估：{exc}。请先在仓库根目录的 .env 中填写对应的 API Key。")
    cases = load_cases(set(args.only.split(",")) if args.only else None)
    print(f"服务商 {llm.provider} · 模型 {llm.model} · {len(cases)} 条用例 × {args.repeat} 次\n")

    sem = asyncio.Semaphore(CONCURRENCY)
    results = await asyncio.gather(
        *(run_case(llm, c, sem) for c in cases for _ in range(args.repeat))
    )

    field_stats: dict[str, list[bool]] = {}
    for r in results:
        if "error" in r:
            print(f"✗ {r['id']:<20} 调用失败：{r['error']}")
            continue
        failed = [k for k, ok in r["checks"].items() if not ok]
        for k, ok in r["checks"].items():
            field_stats.setdefault(k, []).append(ok)
        mark = "✓" if not failed else "✗"
        detail = f"失败：{', '.join(failed)}" if failed else ""
        print(f"{mark} {r['id']:<20} {r['latency_ms']:>6} ms  {detail}")
        for k in failed:
            out = r["output"]
            field = {"role": "role", "no_soft_skills": "tech_stack", "bonus": "bonus",
                     "injection": "summary", "non_empty": "requirements",
                     "no_wrong_company": "company"}.get(k, k)  # fmt: skip
            print(f"    {k}: 模型输出 = {json.dumps(out.get(field), ensure_ascii=False)}")

    total = [ok for v in field_stats.values() for ok in v]
    errors = sum(1 for r in results if "error" in r)
    print("\n按检查项统计：")
    for k, v in sorted(field_stats.items()):
        print(f"  {k:<16} {sum(v)}/{len(v)}  {sum(v) / len(v):.0%}")
    if total:
        acc = sum(total) / len(total)
        print(f"\n整体字段准确率：{sum(total)}/{len(total)} = {acc:.1%}（目标 ≥ 90%）")
    if errors:
        print(f"调用失败：{errors} 次")
    ok_results = [r for r in results if "error" not in r]
    if ok_results:
        tin = sum(r["tokens"][0] for r in ok_results)
        tout = sum(r["tokens"][1] for r in ok_results)
        avg = sum(r["latency_ms"] for r in ok_results) / len(ok_results)
        print(f"token 用量：输入 {tin}，输出 {tout}；平均耗时 {avg:.0f} ms")

    out_dir = EVAL_DIR / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{datetime.now():%Y%m%d-%H%M%S}-{llm.provider}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n详细结果：{out}")


if __name__ == "__main__":
    asyncio.run(main())
