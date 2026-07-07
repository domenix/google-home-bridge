ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.21
FROM ${BUILD_FROM}

ARG CLOUDFLARED_VERSION=2025.6.1
ARG BUILD_ARCH=amd64

RUN pip3 install --no-cache-dir aiohttp==3.12.13

RUN case "${BUILD_ARCH}" in \
        aarch64) CF_ARCH="arm64" ;; \
        amd64) CF_ARCH="amd64" ;; \
        *) echo "Unsupported arch ${BUILD_ARCH}" && exit 1 ;; \
    esac \
    && curl -fsSL -o /usr/local/bin/cloudflared \
        "https://github.com/cloudflare/cloudflared/releases/download/${CLOUDFLARED_VERSION}/cloudflared-linux-${CF_ARCH}" \
    && chmod +x /usr/local/bin/cloudflared

COPY rootfs /

LABEL \
    io.hass.version="1.0.0" \
    io.hass.type="addon" \
    io.hass.arch="aarch64|amd64"
