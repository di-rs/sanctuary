FROM ghcr.io/voidzero-dev/vite-plus:1.7.0 AS frontend
WORKDIR /frontend
COPY --chown=vp:vp tools/cli-playground/frontend/package.json tools/cli-playground/frontend/pnpm-lock.yaml tools/cli-playground/frontend/pnpm-workspace.yaml tools/cli-playground/frontend/.node-version ./
RUN vp install
COPY --chown=vp:vp tools/cli-playground/frontend/ ./
RUN vp build --outDir /frontend/dist

FROM ghcr.io/astral-sh/uv:0.13.9 AS uv
FROM python:3.15-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY tools/cli-playground/pyproject.toml tools/cli-playground/pyproject.toml
COPY tools/cli-playground/src/cli_playground tools/cli-playground/src/cli_playground
COPY --from=frontend /frontend/dist/ tools/cli-playground/src/cli_playground/static/
# CI validates the workspace lock; frozen sync needs only this package's sources.
RUN uv sync --frozen --package cli-playground --no-dev --no-editable --no-python-downloads
FROM python:3.15-slim
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY tools/cli-playground/alembic.ini /app/alembic.ini
ENV PATH="/app/.venv/bin:$PATH"
# Only the trusted image recipe supplies Dokku release commands for PR apps.
RUN printf '%s\n' '#!/bin/sh' \
        'exec uvicorn cli_playground.app:create_app --factory --host 0.0.0.0 --port 8000 --workers 1 --ws-max-size 65536 --no-proxy-headers' \
        > /usr/local/bin/start-playground && chmod +x /usr/local/bin/start-playground && \
    printf '%s\n' 'web: /usr/local/bin/start-playground' 'release: alembic -c /app/alembic.ini upgrade head' > /app/Procfile
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 CMD ["/app/.venv/bin/python", "-c", "import os,urllib.parse,urllib.request; url=urllib.parse.urlsplit(os.environ['CLI_PLAYGROUND_PUBLIC_URL']); req=urllib.request.Request('http://127.0.0.1:8000/healthz',headers={'Host':url.netloc}); urllib.request.urlopen(req,timeout=3).close()"]
CMD ["/usr/local/bin/start-playground"]
