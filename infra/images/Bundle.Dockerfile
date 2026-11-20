FROM rust:bookworm@sha256:ade39a710ef85f3506cffcfec3e8a24ba090badef1dff2fb798f71d878833fea AS rust
FROM ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d AS uv
FROM ubuntu:24.04@sha256:9c7f200c07e3d4a03e7249d2c16bf66a51120fb876aa2242cf31451412543289
COPY --from=rust /usr/local/cargo/bin/rustup /usr/local/bin/rustup
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/python
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git build-essential cmake clang pkg-config libssl-dev && rm -rf /var/lib/apt/lists/* && \
    ln -s rustup /usr/local/bin/cargo && ln -s rustup /usr/local/bin/rustc && \
    uv venv --python 3.15 /opt/catalog && uv pip install --python /opt/catalog/bin/python 'pydantic>=2.14,<3'
COPY infra/control/build_bundle.py /usr/local/bin/build_bundle.py
WORKDIR /source
RUN mkdir -p /work && chown 65532:65532 /work
ENTRYPOINT ["/opt/catalog/bin/python", "/usr/local/bin/build_bundle.py"]
