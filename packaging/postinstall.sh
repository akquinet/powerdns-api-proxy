#!/bin/sh
set -e

if ! getent group powerdns-api-proxy >/dev/null; then
    groupadd --system powerdns-api-proxy
fi
if ! getent passwd powerdns-api-proxy >/dev/null; then
    useradd --system --gid powerdns-api-proxy --no-create-home \
        --home-dir /nonexistent --shell /usr/sbin/nologin powerdns-api-proxy
fi

# Config files ship as root:powerdns-api-proxy, but the user may not have existed
# when the package manager laid them down.
chgrp powerdns-api-proxy /etc/powerdns-api-proxy/config.yml \
    /etc/powerdns-api-proxy/powerdns-api-proxy.env 2>/dev/null || true

if [ -d /run/systemd/system ]; then
    systemctl daemon-reload || true
fi
# Enabled but not started: the config has to be edited first.
systemctl enable powerdns-api-proxy.service >/dev/null 2>&1 || true
