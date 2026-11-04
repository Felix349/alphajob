"""把 FastAPI 的 OpenAPI 文档导出为 JSON 文件，供前端生成 TypeScript 类型。

用法：uv run python scripts/export_openapi.py ../frontend/openapi.json
不需要启动服务器，也不连接数据库。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("openapi.json")
    # newline="\n"：Windows 上也输出 LF，保证和 CI（Linux）生成的文件逐字节一致
    content = json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"
    out.write_text(content, encoding="utf-8", newline="\n")
    print(f"OpenAPI 已导出到 {out.resolve()}")


if __name__ == "__main__":
    main()
