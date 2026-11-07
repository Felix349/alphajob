"""Agent 的工具调用循环（不依赖任何 Agent 框架，大约 100 行）。

    用户消息 ──> 模型 ──有工具调用?──否──> 最终回答，结束
                  ↑          │是
                  │          ↓
                  └── 工具结果 <── 执行每个工具（读工具直接执行；写工具生成“待确认操作”）

每一步都产出一个事件（调用了什么工具、结果如何），通过 SSE 推给前端展示推理过程。
"""

import json
import time
from collections.abc import AsyncIterator

from pydantic import ValidationError

from app.agent import actions
from app.agent.context import AgentContext
from app.agent.tools import TOOLS, ToolError
from app.llm import ChatMessage, LLMClient, LLMError, ToolCall, ToolResult
from app.models import LLMCallLog
from app.prompts.agent import chat_system

MAX_STEPS = 8  # 防止模型陷入“反复调用工具”的死循环
MAX_RESULT_CHARS = 8000  # 工具结果太长会挤占上下文，截断
TOO_MANY_STEPS = "这个问题需要的步骤太多了，我先停在这里。可以换个更具体的问法再试试。"


def _event(kind: str, /, **data) -> dict:
    # kind 是“仅限位置参数”（/）：事件数据里本身就有 name 字段（工具名），不能和它冲突
    return {"event": kind, "data": data}


def _json(data) -> str:
    text = json.dumps(data, ensure_ascii=False, default=str)
    return text if len(text) <= MAX_RESULT_CHARS else text[:MAX_RESULT_CHARS] + "…（已截断）"


def _summary(data) -> str:
    """给前端看的一句话结果摘要，避免把整段 JSON 展示给用户。"""
    if isinstance(data, list):
        return f"返回 {len(data)} 条"
    if isinstance(data, dict):
        return "返回详情"
    return str(data)[:60]


async def _execute(ctx: AgentContext, call: ToolCall) -> tuple[ToolResult, dict]:
    """执行一个工具调用，返回（给模型的结果，给前端的事件）。

    所有错误都转成“错误结果”交还给模型，让它自己修正（比如换一个正确的 id 再调一次），
    而不是中断整个对话。
    """

    def fail(message: str) -> tuple[ToolResult, dict]:
        summary = f"出错：{message[:80]}"
        return ToolResult(call.id, message, True), _event(
            "tool_result", id=call.id, name=call.name, summary=summary, ok=False
        )

    tool = TOOLS.get(call.name)
    if tool is None:
        return fail(f"没有名为 {call.name} 的工具")
    if call.parse_error:
        return fail(call.parse_error)
    try:
        args = tool.args.model_validate(call.arguments)
    except ValidationError as exc:
        return fail(f"参数不正确：{exc.errors(include_url=False)}")

    try:
        if tool.write:
            action = await actions.propose(ctx, call.name, args)
            result = {"status": "等待用户在界面上确认", "action": action.description}
            event = _event(
                "proposal", id=str(action.id), tool=action.tool, description=action.description
            )
            return ToolResult(call.id, _json(result)), event
        data = await tool.run(ctx, args)
    except ToolError as exc:
        return fail(str(exc))
    event = _event("tool_result", id=call.id, name=call.name, summary=_summary(data), ok=True)
    return ToolResult(call.id, _json(data)), event


async def run_agent(
    ctx: AgentContext, llm: LLMClient, history: list[ChatMessage]
) -> AsyncIterator[dict]:
    """产出 SSE 事件：thinking、tool_call、tool_result、proposal、message（最终回答）、error。"""
    session = llm.tool_session(
        system=chat_system(ctx), history=history, tools=[t.spec() for t in TOOLS.values()]
    )
    tokens_in = tokens_out = 0
    start = time.perf_counter()
    error: str | None = None

    try:
        for _ in range(MAX_STEPS):
            turn = await session.step()
            tokens_in += turn.input_tokens
            tokens_out += turn.output_tokens
            if not turn.tool_calls:
                yield _event("message", text=turn.text)
                return
            if turn.text:  # 模型在调用工具前说的话（“我先查一下……”）
                yield _event("thinking", text=turn.text)

            results: list[ToolResult] = []
            for call in turn.tool_calls:
                yield _event("tool_call", id=call.id, name=call.name, arguments=call.arguments)
                result, event = await _execute(ctx, call)
                results.append(result)
                yield event
            session.add_tool_results(results)  # 同一轮的所有结果一起回传

        yield _event("message", text=TOO_MANY_STEPS)
    except LLMError as exc:
        error = str(exc)
        yield _event("error", detail=f"助手出错了：{exc}")
    finally:
        ctx.db.add(
            LLMCallLog(
                user_id=ctx.user.id,
                feature="agent_chat",
                provider=llm.provider,
                model=llm.model,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                success=error is None,
                error=error,
                latency_ms=int((time.perf_counter() - start) * 1000),
            )
        )
        await ctx.db.commit()
