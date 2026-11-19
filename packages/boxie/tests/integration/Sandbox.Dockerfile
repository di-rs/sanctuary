# Generic Boxie fixture: no cli-playground code, fixtures or entrypoint.
FROM ubuntu:24.04@sha256:73b999393d07f2bf65a40373778a44dc9a6d54ad7718d29247d8ff9413c4d6a8
USER 65534:65534
WORKDIR /workspace
CMD ["/bin/sh"]
