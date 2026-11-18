FROM ghcr.io/astral-sh/uv:0.13.9 AS uv
FROM python:3.15-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY packages/boxie/pyproject.toml packages/boxie/pyproject.toml
COPY packages/boxie/src packages/boxie/src
COPY packages/boxie/alembic packages/boxie/alembic
# CI validates the workspace lock; frozen sync needs only this package's sources.
RUN uv sync --frozen --package boxie --no-dev --no-editable --no-python-downloads
FROM python:3.15-slim
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
ARG NATIVE_NOTICE_POLICY=report
RUN --network=none --mount=type=bind,source=infra/distribution,target=/tmp/distribution \
    --mount=type=bind,source=LICENSE,target=/tmp/Sanctuary.LICENSE \
    /app/.venv/bin/python -IS /tmp/distribution/python_notices.py boxie /tmp/Sanctuary.LICENSE /usr/share/sanctuary/notices \
    --native-policy "$NATIVE_NOTICE_POLICY"
ENV PATH="/app/.venv/bin:$PATH"
CMD ["boxie-api", "--config", "/etc/boxie/api.json"]
