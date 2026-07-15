#!/bin/sh
set -eu

APP_IP="$(getent hosts app | awk 'NR == 1 { print $1 }')"
test -n "$APP_IP"
printf '%s\n' "$APP_IP" > /tmp/app_ip

iptables -P OUTPUT DROP
iptables -A OUTPUT -o lo -j ACCEPT
iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -d "$APP_IP"/32 -p tcp --dport 8088 -j ACCEPT

exec su-exec bridge:bridge socat TCP-LISTEN:8088,fork,reuseaddr TCP:"$APP_IP":8088
