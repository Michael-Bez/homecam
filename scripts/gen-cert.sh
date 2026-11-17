#!/usr/bin/env bash
# Generate a self-signed TLS cert for quick testing. The browser will show a warning —
# that is expected. For a trusted cert, use: tailscale cert homecam.<tailnet>.ts.net
set -euo pipefail

CERT_DIR="$(dirname "$0")/../nginx/certs"
mkdir -p "$CERT_DIR"

openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
    -keyout "$CERT_DIR/key.pem" \
    -out    "$CERT_DIR/cert.pem" \
    -subj   "/CN=homecam"

echo "Self-signed cert written to nginx/certs/ (valid 365 days)"
echo "nginx/certs/ is gitignored — regenerate after cloning."
