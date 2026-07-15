FROM alpine:3.22.1
RUN apk add --no-cache iptables socat su-exec \
    && addgroup -g 10001 bridge \
    && adduser -D -H -u 10001 -G bridge bridge
COPY mcp_bridge/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 0555 /usr/local/bin/entrypoint.sh
HEALTHCHECK --interval=10s --timeout=3s --retries=12 CMD ["sh", "-c", "APP_IP=\"$(cat /tmp/app_ip)\" && nc -z \"$APP_IP\" 8088"]
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
