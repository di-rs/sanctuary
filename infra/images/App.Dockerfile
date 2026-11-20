FROM ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d AS uv
FROM node:26-bookworm-slim@sha256:5df79989ed685e09f0a98019db4cebfb22fb9df1a53c0161664a011f7ff6b0f1 AS frontend
WORKDIR /web
COPY tools/cli-playground/frontend/ ./
RUN npm install --global pnpm@12.9.1 && pnpm install --frozen-lockfile && pnpm build

FROM python:3.15-slim-trixie@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928 AS source
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /src
COPY . .
ARG PACKAGE
RUN uv export --locked --package "${PACKAGE}" --extra telemetry --no-dev --no-emit-workspace --format requirements-txt > /tmp/dependencies && \
    uv venv /app && uv pip install --python /app/bin/python --require-hashes -r /tmp/dependencies
FROM source AS boxie-build
RUN uv pip install --python /app/bin/python --no-deps ./packages/boxie
FROM source AS playground-build
COPY --from=frontend /src/cli_playground/static/ tools/cli-playground/src/cli_playground/static/
RUN uv pip install --python /app/bin/python --no-deps ./tools/cli-playground

FROM python:3.15-slim-trixie@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928 AS runtime
ENV PATH=/app/bin:/usr/local/bin:/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
FROM runtime AS boxie
COPY --from=boxie-build /app /app
FROM runtime AS playground
COPY --from=playground-build /app /app
COPY tools/cli-playground/alembic.ini /app/alembic.ini
COPY infra/control/gateway_request.py /app/gateway_request.py
