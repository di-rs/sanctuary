# Vector 0.59 requires journalctl >=258 to resume across host boots.
FROM docker.io/timberio/vector:0.62.0-debian@sha256:6266b1d35c844918ff1c48ea2ec4f57c2b0664c46f3e17fc2418d5dda1692068 AS vector
FROM docker.io/library/ubuntu:26.04@sha256:d66b366dac61b575bee2aef07e9c26e8070096fbe84a3d4d3eb0da069b5d76db
RUN apt-get update \
    && apt-get install -y --no-install-recommends systemd ca-certificates zlib1g libgcc-s1 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/lib/vector \
    && chown 65532:65532 /var/lib/vector
COPY --from=vector /usr/bin/vector /usr/local/bin/vector
USER 65532:65532
ENTRYPOINT ["/usr/local/bin/vector"]
CMD ["--config", "/etc/vector/vector.yaml"]
