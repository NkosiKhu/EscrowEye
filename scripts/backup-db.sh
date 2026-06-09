#!/bin/bash
set -euo pipefail
BACKUP_DIR="${BACKUP_DIR:-/backups}"
DB_PATH="${DB_PATH:-/data/escroweye.sqlite3}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"
sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/escroweye_$TIMESTAMP.sqlite3'"
gzip "$BACKUP_DIR/escroweye_$TIMESTAMP.sqlite3"
find "$BACKUP_DIR" -name "escroweye_*.sqlite3.gz" -mtime +$RETENTION_DAYS -delete
echo "Backup complete: escroweye_$TIMESTAMP.sqlite3.gz"
