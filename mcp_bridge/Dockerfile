FROM alpine:3.22.1
RUN apk add --no-cache iptables socat su-exec \
    && addgroup -g 10001 bridge \
    && adduser -D -H -u 10001 -G bridge bridge
COPY mcp_bridge/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY mcp_bridge/connect-app.sh /usr/local/bin/connect-app.sh
RUN chmod 0555 /usr/local/bin/entrypoint.sh /usr/local/bin/connect-app.sh
HEALTHCHECK --interval=10s --timeout=3s --retries=12 CMD ["sh", "-c", "nc -z 127.0.0.1 8088 && APP_IP=\"$(cat /tmp/app_ip)\" && nc -z \"$APP_IP\" 8088"]
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
