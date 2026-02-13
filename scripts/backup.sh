#!/bin/bash
# Simple backup script for SQLite database
# Run daily via cron: 0 3 * * * /path/to/backup.sh

set -e

# Configuration
PROJECT_DIR="$(dirname "$(dirname "$(readlink -f "$0")")")"
BACKUP_DIR="${PROJECT_DIR}/backups"
DB_FILE="${PROJECT_DIR}/db.sqlite3"
RETENTION_DAYS=30

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Check if database exists
if [ ! -f "$DB_FILE" ]; then
    echo "Database not found: $DB_FILE"
    exit 1
fi

# Create backup with timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/db_${TIMESTAMP}.sqlite3"

# Copy database (SQLite safe backup)
sqlite3 "$DB_FILE" ".backup '${BACKUP_FILE}'"

# Compress backup
gzip "$BACKUP_FILE"

echo "Backup created: ${BACKUP_FILE}.gz"

# Remove old backups
find "$BACKUP_DIR" -name "db_*.sqlite3.gz" -mtime +$RETENTION_DAYS -delete

echo "Old backups cleaned (older than $RETENTION_DAYS days)"
