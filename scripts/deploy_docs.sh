#!/usr/bin/env bash
# Deploy career-scout-mcp.stojadinovic.at static docs to nginx root.
set -euo pipefail
RSYNC_DEST="${RSYNC_DEST:-/var/www/career-scout-mcp/}"
rsync -av --delete \
  --exclude='.git/' --exclude='.*.swp' \
  "$(dirname "$0")/../docs/" "$RSYNC_DEST"
nginx -t && systemctl reload nginx
