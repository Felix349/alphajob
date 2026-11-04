from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import LLMClient
from app.llm.logging import logged_structured
from app.models import User
from app.prompts import jd_parse
from app.schemas.jd import ParsedJD


async def parse_jd(db: AsyncSession, llm: LLMClient, user: User, jd_text: str) -> ParsedJD:
    """把 JD 原文解析成结构化信息。结果不直接保存：前端展示给用户确认、修改后再创建投递记录。"""
    result = await logged_structured(
        db,
        llm,
        user=user,
        feature="parse_jd",
        system=jd_parse.SYSTEM,
        prompt=jd_parse.build_prompt(jd_text.strip()),
        schema=ParsedJD,
        effort="low",  # 信息提取任务，不需要深度推理
    )
    return result.data
