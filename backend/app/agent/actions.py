"""待确认的写操作：Agent 只能“提议”，用户确认后才真正执行。"""

import logging
import uuid

from pydantic import BaseModel
from sqlalchemy import select

from app.agent.context import AgentContext
from app.agent.tools import TOOLS, ToolError
from app.models import AgentAction

log = logging.getLogger(__name__)


class NotFound(Exception):
    pass


class AlreadyHandled(Exception):
    pass


async def propose(ctx: AgentContext, tool_name: str, args: BaseModel) -> AgentAction:
    """生成一条待确认的操作。

    describe() 会校验参数指向的数据存在、且属于当前用户；不满足就抛出 ToolError。
    """
    tool = TOOLS[tool_name]
    description = await tool.describe(ctx, args)  # type: ignore[misc]
    action = AgentAction(
        user_id=ctx.user.id,
        tool=tool_name,
        arguments=args.model_dump(mode="json"),
        description=description,
    )
    ctx.db.add(action)
    await ctx.db.commit()
    await ctx.db.refresh(action)
    return action


async def _require(ctx: AgentContext, action_id: uuid.UUID) -> AgentAction:
    stmt = select(AgentAction).where(
        AgentAction.id == action_id, AgentAction.user_id == ctx.user.id
    )
    action = (await ctx.db.execute(stmt)).scalar_one_or_none()
    if action is None:
        raise NotFound
    if action.status != "pending":
        raise AlreadyHandled  # 防止重复点击确认导致执行两次
    return action


async def confirm(ctx: AgentContext, action_id: uuid.UUID) -> AgentAction:
    action = await _require(ctx, action_id)
    tool = TOOLS[action.tool]
    # 先记下用户 id：rollback 之后所有已加载的对象都会过期，再读属性会触发同步查询而报错
    user_id = ctx.user.id
    try:
        # 执行时重新校验一遍参数：从提议到确认之间，数据可能已经被删除或修改
        args = tool.args.model_validate(action.arguments)
        action.result = await tool.run(ctx, args)
        action.status = "done"
    except Exception as exc:  # 执行失败要告诉用户，而不是让请求报 500
        log.warning("执行 Agent 操作 %s 失败：%s", action_id, exc)
        await ctx.db.rollback()
        stmt = select(AgentAction).where(
            AgentAction.id == action_id, AgentAction.user_id == user_id
        )
        action = (await ctx.db.execute(stmt)).scalar_one()
        action.status = "failed"
        action.result = str(exc) if isinstance(exc, ToolError) else "执行失败，相关数据可能已被删除"
    await ctx.db.commit()
    await ctx.db.refresh(action)
    return action


async def cancel(ctx: AgentContext, action_id: uuid.UUID) -> AgentAction:
    action = await _require(ctx, action_id)
    action.status = "cancelled"
    await ctx.db.commit()
    await ctx.db.refresh(action)
    return action
