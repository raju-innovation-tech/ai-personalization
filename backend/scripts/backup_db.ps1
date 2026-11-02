# Automated PostgreSQL database backup script for Windows environments.
param(
    [string]$BackupDir = "$PSScriptRoot\..\backups",
    [int]$RetentionDays = 14
)

$ErrorActionPreference = 'Stop'
$Timestamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}

$BackupFile = Join-Path $BackupDir "aip_backup_$Timestamp.sql"
Write-Host "📦 Starting PostgreSQL backup to $BackupFile..."

# Execute pg_dump inside container
docker compose exec -T postgres pg_dump -U raju -d ai_personalization -F c -b -v -f "/tmp/backup.dump"
docker cp aip_postgres:/tmp/backup.dump "$BackupFile.dump"

Write-Host "✅ Backup created successfully: $BackupFile.dump"

# Cleanup old backups
Get-ChildItem -Path $BackupDir -Filter "*.dump" | Where-Object { $_.CreationTime -lt (Get-Date).AddDays(-$RetentionDays) } | ForEach-Object {
    Write-Host "🗑️ Removing old backup: $($_.Name)"
    Remove-Item $_.FullName -Force
}
