"""路由共用的依赖：当前登录用户、大模型客户端。"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import decode_access_token
from app.llm import LLMClient, LLMNotConfigured
from app.llm.factory import get_llm_client
from app.models import User
from app.repositories import users as users_repo

# 流式（SSE）响应的响应头：防止中间环节把流攒起来再一次性发出
# - X-Accel-Buffering: no —— 告诉 Nginx 之类的反向代理不要缓冲
# - no-transform —— 告诉代理和压缩中间件不要改动响应。Next.js 生产服务器默认 gzip 压缩，
#   而压缩会把整个流攒到最后才发出（Docker 一键启动时实测：18 秒后一次性收到全部内容）
SSE_HEADERS = {"X-Accel-Buffering": "no", "Cache-Control": "no-cache, no-transform"}


def require_llm() -> LLMClient:
    """拿到配置好的大模型客户端；没配 API Key 时返回 503，前端据此提示用户。
    测试中通过 app.dependency_overrides[require_llm] 替换成假的实现。"""
    try:
        return get_llm_client()
    except LLMNotConfigured as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"AI 功能暂不可用：{exc}"
        ) from None


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已过期"
    )
    token = request.cookies.get(get_settings().cookie_name)
    if not token:
        raise unauthorized
    user_id = decode_access_token(token)
    if user_id is None:
        raise unauthorized
    user = await users_repo.get_by_id(db, user_id)
    if user is None:  # token 有效但用户已被删除
        raise unauthorized
    return user
