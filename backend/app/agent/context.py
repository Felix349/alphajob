from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User

DEFAULT_TZ = "Asia/Shanghai"
WEEKDAYS = "一二三四五六日"


def resolve_tz(name: str | None) -> ZoneInfo:
    """前端传来的时区名（如 Asia/Shanghai）不可信，无效时退回默认时区。"""
    try:
        return ZoneInfo(name or DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TZ)


@dataclass
class AgentContext:
    """工具执行时需要的一切：数据库会话、当前用户、用户所在时区。

    工具只能通过 ctx.user 访问数据，所以天然只能看到、改到“当前用户”自己的数据。
    """

    db: AsyncSession
    user: User
    tz: ZoneInfo

    def now(self) -> datetime:
        return datetime.now(self.tz)

    def fmt(self, dt: datetime | None) -> str | None:
        """把时间转成用户本地时间的易读格式：11-07 周五 14:00。模型和用户都看这个格式。"""
        if dt is None:
            return None
        local = dt.astimezone(self.tz)
        return f"{local:%m-%d} 周{WEEKDAYS[local.weekday()]} {local:%H:%M}"
