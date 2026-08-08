#!/bin/sh
set -e

# One-time migration: if a bundled database ships with the repo and the
# persistent volume is empty, copy it there on the first boot.
if [ -n "$BOT_DATABASE_PATH" ] && [ ! -f "$BOT_DATABASE_PATH" ] && [ -f "group_dice_royale.db" ]; then
    echo "Copying bundled database to $BOT_DATABASE_PATH"
    mkdir -p "$(dirname "$BOT_DATABASE_PATH")"
    cp group_dice_royale.db "$BOT_DATABASE_PATH"
fi

exec python casino_royals_bot.py
