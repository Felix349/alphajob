import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class Resume(IdMixin, TimestampMixin, Base):
    """用户的简历。v0.1 每个用户一份（user_id 唯一），统一存成 Markdown 文本。

    PDF 上传后会先提取成文本，用户可以在页面上继续修改：模型读的是这份文本，不是 PDF 本身。
    """

    __tablename__ = "resumes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    content_md: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual / pdf
    filename: Mapped[str | None] = mapped_column(String(255))
