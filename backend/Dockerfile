# 后端镜像：API、Worker、数据库迁移共用这一个镜像，只是启动命令不同（见 docker-compose.yml）
FROM python:3.12-slim

# Debian 软件源：默认官方源；国内网络连不上时，在 .env 里设 APT_MIRROR=mirrors.aliyun.com
ARG APT_MIRROR=deb.debian.org
RUN sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources

# ffmpeg：面试录音转写前，先把音频转成 16k 单声道 wav
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.10.6 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# 先只装依赖：依赖不变时，改代码重新构建会直接用缓存，不用重新下载
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .
RUN uv sync --locked --no-dev

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
