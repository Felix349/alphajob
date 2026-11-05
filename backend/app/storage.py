"""文件存储：v0.1 存在本地目录（Docker 部署时挂载为数据卷）。

对外只暴露“相对路径”，以后换成对象存储（OSS / S3）时，调用方不用改。
"""

import uuid
from pathlib import Path

from app.core.config import get_settings


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root

    def save(self, user_id: uuid.UUID, data: bytes, suffix: str) -> str:
        """保存文件，返回相对路径。文件名用随机 UUID：不信任用户上传的文件名，也避免重名覆盖。"""
        rel = Path(str(user_id)) / f"{uuid.uuid4().hex}{suffix.lower()}"
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return rel.as_posix()

    def path(self, rel: str) -> Path:
        resolved = (self.root / rel).resolve()
        # 防止 “../../etc/passwd” 这类路径穿越：解析后必须仍在存储根目录下
        if not resolved.is_relative_to(self.root.resolve()):
            raise ValueError("非法的存储路径")
        return resolved

    def delete(self, rel: str) -> None:
        self.path(rel).unlink(missing_ok=True)


def get_storage() -> LocalStorage:
    return LocalStorage(get_settings().upload_dir)
