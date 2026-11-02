#!/usr/bin/env bash
# Automated PostgreSQL database backup script for Linux/macOS environments.
set -euo pipefail

BACKUP_DIR="${1:-./backups}"
RETENTION_DAYS=14
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/aip_backup_${TIMESTAMP}.dump"

mkdir -p "${BACKUP_DIR}"
echo "📦 Backing up PostgreSQL database to ${BACKUP_FILE}..."

docker compose exec -T postgres pg_dump -U raju -d ai_personalization -F c -b -f "/tmp/backup.dump"
docker cp aip_postgres:/tmp/backup.dump "${BACKUP_FILE}"

echo "✅ Backup completed: ${BACKUP_FILE}"

# Remove backups older than 14 days
find "${BACKUP_DIR}" -name "*.dump" -type f -mtime +${RETENTION_DAYS} -exec rm -f {} \;
echo "🧹 Pruned backups older than ${RETENTION_DAYS} days."
