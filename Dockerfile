FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ARG APT_MIRROR=mirrors.tuna.tsinghua.edu.cn
ARG APT_MIRROR_FALLBACK=deb.debian.org
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_INDEX_URL_FALLBACK=https://pypi.org/simple
ARG DENO_VERSION=2.8.1

ENV PIP_INDEX_URL=${PIP_INDEX_URL}

RUN set -e; \
    cp /etc/apt/sources.list.d/debian.sources /tmp/debian.sources; \
    configure_apt_mirror() { \
        cp /tmp/debian.sources /etc/apt/sources.list.d/debian.sources; \
        sed -i -E "s#https?://deb.debian.org/debian#https://$1/debian#g; s#https?://deb.debian.org/debian-security#https://$1/debian-security#g" /etc/apt/sources.list.d/debian.sources; \
    }; \
    APT_HOST="${APT_MIRROR}"; \
    if ! getent hosts "$APT_HOST" >/dev/null 2>&1; then \
        echo "APT mirror ${APT_HOST} not resolvable, falling back to ${APT_MIRROR_FALLBACK}"; \
        APT_HOST="${APT_MIRROR_FALLBACK}"; \
    fi; \
    configure_apt_mirror "$APT_HOST"; \
    if ! apt-get update; then \
        if [ "$APT_HOST" = "${APT_MIRROR_FALLBACK}" ]; then \
            exit 1; \
        fi; \
        echo "APT mirror ${APT_HOST} unavailable, falling back to ${APT_MIRROR_FALLBACK}"; \
        rm -rf /var/lib/apt/lists/*; \
        configure_apt_mirror "${APT_MIRROR_FALLBACK}"; \
        apt-get update; \
    fi; \
    apt-get install -y --no-install-recommends ffmpeg ca-certificates curl unzip; \
    rm -f /tmp/debian.sources; \
    rm -rf /var/lib/apt/lists/*

ARG TARGETARCH
RUN set -e; \
    case "${TARGETARCH}" in \
        amd64) DENO_ARCH="x86_64-unknown-linux-gnu" ;; \
        arm64) DENO_ARCH="aarch64-unknown-linux-gnu" ;; \
        *) echo "Unsupported Docker architecture for Deno: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    DENO_BASE="https://github.com/denoland/deno/releases/download/v${DENO_VERSION}/deno-${DENO_ARCH}"; \
    curl --fail --silent --show-error --location "${DENO_BASE}.zip" -o /tmp/deno.zip; \
    curl --fail --silent --show-error --location "${DENO_BASE}.zip.sha256sum" -o /tmp/deno.zip.sha256sum; \
    printf '%s  /tmp/deno.zip\n' "$(cut -d ' ' -f1 /tmp/deno.zip.sha256sum)" | sha256sum -c -; \
    unzip -q /tmp/deno.zip deno -d /usr/local/bin; \
    chmod 0755 /usr/local/bin/deno; \
    deno --version; \
    rm -f /tmp/deno.zip /tmp/deno.zip.sha256sum

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
    if ! pip install --no-cache-dir -r requirements.txt -i "$PIP_URL"; then \
        if [ "$PIP_URL" = "${PIP_INDEX_URL_FALLBACK}" ]; then \
            exit 1; \
        fi; \
        echo "PIP mirror ${PIP_URL} unavailable, falling back to ${PIP_INDEX_URL_FALLBACK}"; \
        PIP_URL="${PIP_INDEX_URL_FALLBACK}"; \
        pip install --no-cache-dir -r requirements.txt -i "$PIP_URL"; \
    fi; \
    PIP_INDEX_URL="$PIP_URL" pip install --no-cache-dir --no-deps .

ENV DOWNLOAD_DIR=/downloads
ENV DOWNLOAD_ROOT_DIR=/downloads
ENV VIDEO_DOWNLOADE_CONFIG_DIR=/config
EXPOSE 5657
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"5657\")}/', timeout=5)"

CMD ["muku", "serve", "--host", "0.0.0.0", "--port", "5657"]
