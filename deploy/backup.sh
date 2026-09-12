#!/bin/bash
# Database backup script for Cantateo
# Add to crontab: 0 3 * * * /var/www/cantateo/deploy/backup.sh
# Runs daily at 3 AM

set -e

BACKUP_DIR="/var/backups/cantateo"
DB_NAME="cantateo"
DB_USER="cantateo"
RETENTION_DAYS=7
BACKUP_REMOTE_TARGET="${BACKUP_REMOTE_TARGET:-}"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Generate backup filename with timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.sql.gz"

# Create backup
echo "[$(date)] Starting backup..."
pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_FILE"

# Verify backup was created
if [ -f "$BACKUP_FILE" ]; then
    gzip -t "$BACKUP_FILE"
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "[$(date)] Backup created: $BACKUP_FILE ($SIZE)"
else
    echo "[$(date)] ERROR: Backup failed!"
    exit 1
fi

if [ -n "$BACKUP_REMOTE_TARGET" ]; then
    echo "[$(date)] Copying backup to remote target..."
    rsync -az "$BACKUP_FILE" "$BACKUP_REMOTE_TARGET/"
fi

# Remove old backups
echo "[$(date)] Removing backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete

# List remaining backups
echo "[$(date)] Current backups:"
ls -lh "$BACKUP_DIR"/*.sql.gz 2>/dev/null || echo "No backups found"

echo "[$(date)] Backup complete."
