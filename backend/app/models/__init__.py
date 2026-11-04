"""所有表模型在这里汇总导入，Alembic 通过 Base.metadata 发现它们。"""

from app.models.base import Base
from app.models.user import User

__all__ = ["Base", "User"]
