ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.21
FROM ${BUILD_FROM}

RUN pip3 install --no-cache-dir aiohttp==3.12.13

COPY rootfs /

LABEL \
    io.hass.version="1.1.0" \
    io.hass.type="addon" \
    io.hass.arch="aarch64|amd64"
