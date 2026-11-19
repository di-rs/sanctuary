# Match the Ubuntu 24.04 GitHub runner that builds the native Linux binaries.
FROM ubuntu:24.04@sha256:73b999393d07f2bf65a40373778a44dc9a6d54ad7718d29247d8ff9413c4d6a8
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash coreutils findutils grep sed gawk less libgcc-s1 \
    && rm -rf /var/lib/apt/lists/*
COPY packages/boxie/sandbox/fixtures/ /opt/fixtures/
COPY packages/boxie/sandbox/shell.sh /opt/boxie/shell.sh
RUN chmod 0555 /opt/boxie/shell.sh
USER 65534:65534
WORKDIR /workspace
ENTRYPOINT ["/opt/boxie/shell.sh"]
