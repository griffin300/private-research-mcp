#!/bin/sh
set -eu

APP_IP="$(cat /tmp/app_ip)"
case "$APP_IP" in
    ''|*[!0-9.]*) exit 1 ;;
esac

exec socat STDIO TCP4:"$APP_IP":8088,connect-timeout=5
