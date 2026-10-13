#!/bin/sh
set -e

# $1 is "0" (rpm) or "remove" (deb) on real removal, not on upgrade.
case "$1" in
    0|remove)
        systemctl stop powerdns-api-proxy.service >/dev/null 2>&1 || true
        systemctl disable powerdns-api-proxy.service >/dev/null 2>&1 || true
        ;;
esac
