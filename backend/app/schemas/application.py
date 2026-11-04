import uuid
from datetime import date, datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.models import EventType, Stage
from app.schemas.jd import ParsedJD

# ---------- 日程事件 ----------


class EventBase(BaseModel):
    type: EventType
    title: str = Field(min_length=1, max_length=128)
    # AwareDatetime：必须带时区，避免“服务器时区”和“用户时区”混淆
    start_at: AwareDatetime
    end_at: AwareDatetime | None = None
    link: str | None = Field(default=None, max_length=1024)
    note: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def end_after_start(self):
        if self.end_at is not None and self.end_at < self.start_at:
            raise ValueError("结束时间不能早于开始时间")
        return self


class EventCreate(EventBase):
    pass


class EventUpdate(BaseModel):
    type: EventType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=128)
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None
    link: str | None = Field(default=None, max_length=1024)
    note: str | None = Field(default=None, max_length=5000)


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    type: EventType
    title: str
    start_at: datetime
    end_at: datetime | None
    link: str | None
    note: str | None


class CalendarEventOut(EventOut):
    """日历视图用：带上所属投递的公司和岗位，前端不用再单独请求。"""

    company: str
    role: str
    stage: Stage


# ---------- 投递记录 ----------


class ApplicationCreate(BaseModel):
    company: str = Field(min_length=1, max_length=128)
    role: str = Field(min_length=1, max_length=128)
    location: str | None = Field(default=None, max_length=128)
    channel: str | None = Field(default=None, max_length=64)
    job_url: str | None = Field(default=None, max_length=1024)
    jd_text: str | None = Field(default=None, max_length=20000)
    jd_parsed: ParsedJD | None = None
    stage: Stage = Stage.WISHLIST
    applied_at: date | None = None
    notes: str | None = Field(default=None, max_length=10000)


class ApplicationUpdate(BaseModel):
    """PATCH：只更新请求里出现的字段（exclude_unset）。拖拽改阶段也走这里。"""

    company: str | None = Field(default=None, min_length=1, max_length=128)
    role: str | None = Field(default=None, min_length=1, max_length=128)
    location: str | None = Field(default=None, max_length=128)
    channel: str | None = Field(default=None, max_length=64)
    job_url: str | None = Field(default=None, max_length=1024)
    jd_text: str | None = Field(default=None, max_length=20000)
    jd_parsed: ParsedJD | None = None
    stage: Stage | None = None
    position: float | None = None
    applied_at: date | None = None
    notes: str | None = Field(default=None, max_length=10000)


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company: str
    role: str
    location: str | None
    channel: str | None
    job_url: str | None
    stage: Stage
    position: float
    applied_at: date | None
    created_at: datetime
    updated_at: datetime
    # 看板卡片上显示“下一场”：最近一个尚未开始的日程
    next_event: EventOut | None = None


class ApplicationDetail(ApplicationOut):
    jd_text: str | None
    jd_parsed: ParsedJD | None
    notes: str | None
    events: list[EventOut]
