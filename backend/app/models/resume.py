import uuid
from typing import Literal

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin

ResumeLanguage = Literal["zh", "en"]
RESUME_LANGUAGES: tuple[ResumeLanguage, ...] = ("zh", "en")


class Resume(IdMixin, TimestampMixin, Base):
    """用户的简历，统一存成 Markdown 文本。每个用户最多两份：中文一份、英文一份。

    PDF 上传后会先提取成文本，用户可以在页面上继续修改：模型读的是这份文本，不是 PDF 本身。
    """

    __tablename__ = "resumes"
    # 唯一约束从“每个用户一份”改为“每个用户、每种语言一份”
    __table_args__ = (UniqueConstraint("user_id", "language", name="uq_resumes_user_language"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # server_default：迁移时，已经存在的简历自动视为中文简历
    language: Mapped[str] = mapped_column(String(8), default="zh", server_default="zh")
    content_md: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual / pdf
    filename: Mapped[str | None] = mapped_column(String(255))
