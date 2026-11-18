# Vector 0.59 requires journalctl >=258 to resume across host boots.
FROM docker.io/timberio/vector:0.61.0-debian@sha256:f6c23b5a7e16fb2838d33619ef7acf4bad2289a7cf22bc90efc2371f520c4ea2 AS vector
FROM docker.io/library/ubuntu:26.04@sha256:f144425ff09be612d6d9ad965196e9cdc23dae1f42110a8a11a3e9a8198759f7
RUN apt-get update \
    && apt-get install -y --no-install-recommends systemd ca-certificates zlib1g libgcc-s1 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/lib/vector \
    && chown 65532:65532 /var/lib/vector
COPY --from=vector /usr/bin/vector /usr/local/bin/vector
COPY --from=vector /usr/share/doc/vector/copyright /usr/share/sanctuary/notices/vector/copyright
COPY --from=vector /usr/share/vector/NOTICE /usr/share/vector/LICENSE-3rdparty.csv /usr/share/sanctuary/notices/vector/
COPY --from=vector /usr/share/vector/licenses/ /usr/share/sanctuary/notices/vector/licenses/
RUN test -s /usr/share/sanctuary/notices/vector/copyright \
    && test -s /usr/share/sanctuary/notices/vector/NOTICE \
    && test -s /usr/share/sanctuary/notices/vector/LICENSE-3rdparty.csv \
    && test -s /usr/share/sanctuary/notices/vector/licenses/MPL-2.0
USER 65532:65532
ENTRYPOINT ["/usr/local/bin/vector"]
CMD ["--config", "/etc/vector/vector.yaml"]
