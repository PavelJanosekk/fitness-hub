#!/bin/sh
# Daily pg_dump with 7 daily / 4 weekly / 6 monthly rotation (docs/SPEC.md §3, A11).
# Runs in the `backup` compose service (postgres:16-alpine, same major as the server). Connection comes from
# the libpq env vars PGHOST/PGUSER/PGPASSWORD/PGDATABASE. Restore steps: docs/operations.md.
set -u
umask 077

DIR=/backups
HOUR=${BACKUP_HOUR:-3}
KEEP_DAILY=${BACKUP_KEEP_DAILY:-7}
KEEP_WEEKLY=${BACKUP_KEEP_WEEKLY:-4}
KEEP_MONTHLY=${BACKUP_KEEP_MONTHLY:-6}
PREFIX=fitness-hub

log() { echo "backup: $*"; }

# Keep the newest $2 dumps in $DIR/$1 (ISO dates in the names sort chronologically)
prune() {
    ls -1 "$DIR/$1"/*.dump 2>/dev/null | sort -r | tail -n +"$(($2 + 1))" | while read -r old; do
        rm -f "$old" && log "pruned $old"
    done
}

backup() {
    daily="$DIR/daily/$PREFIX-$(date +%F).dump"
    if ! pg_dump --format=custom --file="$daily.tmp"; then
        rm -f "$daily.tmp"
        log "FAILED, retrying in 10 min" >&2
        return 1
    fi
    mv "$daily.tmp" "$daily"
    log "wrote $daily ($(du -h "$daily" | cut -f1))"
    # The first dump of each ISO week / month is kept as that period's copy (hard link, no extra space)
    weekly="$DIR/weekly/$PREFIX-$(date +%G-W%V).dump"
    monthly="$DIR/monthly/$PREFIX-$(date +%Y-%m).dump"
    [ -e "$weekly" ] || ln "$daily" "$weekly"
    [ -e "$monthly" ] || ln "$daily" "$monthly"
    prune daily "$KEEP_DAILY"
    prune weekly "$KEEP_WEEKLY"
    prune monthly "$KEEP_MONTHLY"
}

mkdir -p "$DIR/daily" "$DIR/weekly" "$DIR/monthly" || exit 1
rm -f "$DIR"/daily/*.tmp
log "daily at ${HOUR}:00 $(date +%Z), keeping $KEEP_DAILY daily / $KEEP_WEEKLY weekly / $KEEP_MONTHLY monthly"

# Check every 10 min: today's dump is due once it is past HOUR, or right away when the newest is over 24 h old
# (first start, or the server was off at HOUR). Polling instead of sleeping until HOUR survives DST and suspend.
while :; do
    if [ ! -e "$DIR/daily/$PREFIX-$(date +%F).dump" ]; then
        if [ "$(date +%H)" -ge "$HOUR" ] || [ -z "$(find "$DIR/daily" -name '*.dump' -mmin -1440)" ]; then
            backup
        fi
    fi
    sleep 600
done
