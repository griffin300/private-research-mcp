#!/bin/sh
set -eu

APP_PORT=8088
APP_HOST=app
APP_CHAIN=BRIDGE_APP_EGRESS
REFRESH_SECONDS="${PRM_BRIDGE_DNS_REFRESH_SECONDS:-1}"

is_ipv4() {
    printf '%s\n' "$1" | awk -F. '
        NF != 4 { exit 1 }
        {
            for (i = 1; i <= 4; i++) {
                if ($i !~ /^[0-9]+$/ || $i < 0 || $i > 255) exit 1
            }
        }
    '
}

resolve_app_ip() {
    getent hosts "$APP_HOST" 2>/dev/null | awk '{ print $1 }' | while IFS= read -r candidate; do
        if is_ipv4 "$candidate"; then
            printf '%s\n' "$candidate"
            break
        fi
    done
}

direct_route_device() {
    route="$(ip -4 route get "$1" 2>/dev/null || true)"
    case " $route " in
        *' via '*) return 1 ;;
    esac
    printf '%s\n' "$route" | awk '
        NR == 1 {
            for (i = 1; i < NF; i++) {
                if ($i == "dev") { print $(i + 1); exit }
            }
        }
    '
}

write_app_ip() {
    next_file="/tmp/app_ip.next.$$"
    umask 022
    printf '%s\n' "$1" > "$next_file"
    chmod 0444 "$next_file"
    mv -f "$next_file" /tmp/app_ip
}

allow_app_ip() {
    new_ip="$1"
    old_ip="${APP_IP:-}"
    if [ "$new_ip" = "$old_ip" ]; then
        return
    fi

    # Permit the replacement before publishing it, then remove the old target.
    # Every connection remains allowlisted during an app-IP transition.
    iptables -A "$APP_CHAIN" -d "$new_ip"/32 -p tcp --dport "$APP_PORT" -j ACCEPT
    write_app_ip "$new_ip"
    if [ -n "$old_ip" ]; then
        iptables -D "$APP_CHAIN" -d "$old_ip"/32 -p tcp --dport "$APP_PORT" -j ACCEPT
    fi
    APP_IP="$new_ip"
}

DNS_IP="$(awk '$1 == "nameserver" { print $2; exit }' /etc/resolv.conf)"
if ! is_ipv4 "$DNS_IP"; then
    printf '%s\n' 'bridge startup failed: Docker DNS did not provide an IPv4 resolver' >&2
    exit 1
fi

case "$REFRESH_SECONDS" in
    ''|*[!0-9]*)
        printf '%s\n' 'bridge startup failed: refresh interval must be an integer' >&2
        exit 1
        ;;
esac
if [ "$REFRESH_SECONDS" -lt 1 ] || [ "$REFRESH_SECONDS" -gt 60 ]; then
    printf '%s\n' 'bridge startup failed: refresh interval must be between 1 and 60 seconds' >&2
    exit 1
fi

iptables -P OUTPUT DROP
iptables -F OUTPUT
iptables -F "$APP_CHAIN" 2>/dev/null || true
iptables -X "$APP_CHAIN" 2>/dev/null || true
iptables -N "$APP_CHAIN"
# Docker DNATs 127.0.0.11:53 to an ephemeral loopback port before the filter
# chain. Restrict that loopback resolver address to the root watcher instead of
# allowing DNS to the network-facing bridge user.
iptables -A OUTPUT -m owner --uid-owner 0 -d "$DNS_IP"/32 -p udp -j ACCEPT
iptables -A OUTPUT -m owner --uid-owner 0 -d "$DNS_IP"/32 -p tcp -j ACCEPT
iptables -A OUTPUT -o lo -p tcp --dport "$APP_PORT" -j ACCEPT
iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -j "$APP_CHAIN"

APP_IP=''
APP_DEVICE=''
while [ -z "$APP_IP" ]; do
    candidate="$(resolve_app_ip || true)"
    candidate_device="$(direct_route_device "$candidate" || true)"
    if [ -n "$candidate" ] && [ -n "$candidate_device" ]; then
        APP_DEVICE="$candidate_device"
        allow_app_ip "$candidate"
    else
        sleep "$REFRESH_SECONDS"
    fi
done

watch_app_ip() {
    # If the privileged watcher itself fails, stop PID 1 so Docker's existing
    # restart policy rebuilds both the firewall and target state from scratch.
    trap 'kill -TERM 1 2>/dev/null || true' EXIT
    while :; do
        sleep "$REFRESH_SECONDS"
        candidate="$(resolve_app_ip || true)"
        candidate_device="$(direct_route_device "$candidate" || true)"
        if [ -n "$candidate" ] && [ "$candidate_device" = "$APP_DEVICE" ]; then
            allow_app_ip "$candidate"
        fi
    done
}

watch_app_ip &
exec su-exec bridge:bridge socat \
    TCP4-LISTEN:"$APP_PORT",fork,reuseaddr \
    EXEC:/usr/local/bin/connect-app.sh,nofork
