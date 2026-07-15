FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends tor netcat-openbsd ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY torrc /etc/tor/torrc
USER debian-tor
HEALTHCHECK --interval=10s --timeout=3s --retries=12 CMD ["nc", "-z", "127.0.0.1", "9050"]
CMD ["tor", "-f", "/etc/tor/torrc"]
