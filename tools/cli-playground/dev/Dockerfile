FROM rust:slim-bookworm AS clis
WORKDIR /src
COPY rust-toolchain.toml ./
RUN rustup show
ARG CLI_PACKAGES
ENV CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_DEV_STRIP=symbols CARGO_TARGET_DIR=/build
RUN --mount=type=bind,target=/src \
    --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/build \
    set -ef; set -- --workspace; \
    if [ -n "$CLI_PACKAGES" ]; then \
      set --; for name in $CLI_PACKAGES; do set -- "$@" --package "$name"; done; \
    fi; \
    cargo -Z unstable-options build --locked --bins "$@" --artifact-dir /out

FROM ghcr.io/voidzero-dev/vite-plus:1.2.0 AS frontend
WORKDIR /frontend
COPY --chown=vp:vp tools/cli-playground/frontend/ ./
RUN vp install --frozen-lockfile && vp build --outDir /frontend/dist

FROM ghcr.io/astral-sh/uv:0.13.0 AS uv
FROM python:3.15-slim AS python
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY packages/boxie/ packages/boxie/
COPY tools/cli-playground/ tools/cli-playground/
RUN uv sync --frozen --package cli-playground --package boxie-test-support --no-dev --no-python-downloads

FROM python:3.15-slim
WORKDIR /app/tools/cli-playground
COPY --from=python /app /app
COPY --from=clis /out/ /opt/artifact/
COPY --from=frontend /frontend/dist/ /app/tools/cli-playground/src/cli_playground/static/
COPY packages/boxie/sandbox/fixtures/ /opt/fixtures/
ENV PATH="/app/.venv/bin:/usr/local/bin:/usr/bin:/bin" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN install -d -o 1000 -g 1000 -m 0700 /var/lib/playground-sessions
USER 1000:1000
CMD ["python", "-m", "tests.dev_server"]
