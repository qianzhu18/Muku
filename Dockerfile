FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ARG APT_MIRROR=mirrors.tuna.tsinghua.edu.cn
ARG APT_MIRROR_FALLBACK=deb.debian.org
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_INDEX_URL_FALLBACK=https://pypi.org/simple

ENV PIP_INDEX_URL=${PIP_INDEX_URL}

RUN set -e; \
    APT_HOST="${APT_MIRROR}"; \
    if ! getent hosts "$APT_HOST" >/dev/null 2>&1; then \
        echo "APT mirror ${APT_HOST} not resolvable, falling back to ${APT_MIRROR_FALLBACK}"; \
        APT_HOST="${APT_MIRROR_FALLBACK}"; \
    fi; \
    sed -i.bak -E "s#http://deb.debian.org/debian#https://${APT_HOST}/debian#g; s#http://deb.debian.org/debian-security#https://${APT_HOST}/debian-security#g" /etc/apt/sources.list.d/debian.sources; \
    apt-get update; \
    apt-get install -y --no-install-recommends ffmpeg ca-certificates; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md requirements.txt ./
COPY webui/ /app/webui/
COPY 角色提示词.md /app/角色提示词.md
COPY 解析提示词.md /app/解析提示词.md
COPY 知识库提示词.md /app/知识库提示词.md
RUN set -e; \
    PIP_URL="${PIP_INDEX_URL}"; \
    PIP_HOST=$(echo "$PIP_URL" | sed -E 's#^https?://##; s#/.*##'); \
    if ! getent hosts "$PIP_HOST" >/dev/null 2>&1; then \
        echo "PIP mirror ${PIP_HOST} not resolvable, falling back to ${PIP_INDEX_URL_FALLBACK}"; \
        PIP_URL="${PIP_INDEX_URL_FALLBACK}"; \
    fi; \
    pip install --no-cache-dir -r requirements.txt -i "$PIP_URL"; \
    pip install --no-cache-dir --no-deps .

ENV DOWNLOAD_DIR=/downloads
ENV DOWNLOAD_ROOT_DIR=/downloads
ENV VIDEO_DOWNLOADE_CONFIG_DIR=/config
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8080\")}/', timeout=5)"

CMD ["video-downloade", "serve", "--host", "0.0.0.0", "--port", "8080"]
