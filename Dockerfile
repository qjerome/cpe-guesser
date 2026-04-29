# syntax=docker/dockerfile:1

FROM alpine:latest

COPY . /app

RUN rm -rf /app/.venv

RUN <<EOF
apk update
apk add uv
apk add expect
apk add curl
EOF

# Disable development dependencies
ENV UV_NO_DEV=1

WORKDIR /app

RUN uv sync --locked

# configuration
COPY <<EOF /app/config/config.yaml
server:
  port: 8000
valkey:
  host: valkey
  port: 6379
  db: 8
downloads:
    path: '/data/'
EOF

# entrypoint script
COPY <<'EOF' entrypoint.sh
#!/bin/ash
set -eux

unbuffer uv run cpe-import --format nvd-json https://nvd.nist.gov/feeds/json/cpe/2.0/nvdcpe-2.0.tar.gz &
unbuffer uv run cpe-import --force --format any-text https://vulnerability.circl.lu/dumps/cvelistv5.ndjson &

echo "Running cpe-server"
uv run cpe-server
EOF

RUN chmod u+x entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
