# Casino Royals Bot — Railway Deployment

Single-file Telegram casino bot (crypto-only deposits, admin panel, channel
settings, /backup). Python 3.9+, python-telegram-bot 22.7, Pillow.

## Files

| File | Purpose |
|---|---|
| `casino_royals_bot.py` | The bot (single self-contained file) |
| `requirements.txt` | Lets Railpack detect Python + installs dependencies |
| `start.sh` | Start command (also migrates a bundled DB to a volume on first boot) |
| `railway.json` | Railway start command / restart policy |
| `smoke_test.py` | Optional test suite (`python3 smoke_test.py`) |

## Deploy to Railway (zip upload)

1. Upload `casino_royals_bot_bundle.zip` (or the folder with all files above)
   to your Railway project → **Deploy**.
2. Railway/Railpack now detects Python via `requirements.txt`, installs
   `python-telegram-bot==22.7` + Pillow, and runs `sh start.sh` → the bot.
3. Set the environment variable in Railway → **Variables**:
   - `TELEGRAM_BOT_TOKEN` = your bot token (optional, but recommended —
     overrides the token embedded in the script)
   - `BOT_ADMIN_IDS` = comma-separated owner ID(s) (optional override)
   - `BOT_DATABASE_PATH` = e.g. `/data/group_dice_royale.db`
4. **Persistent data (important):** Railway's filesystem is ephemeral — files
   written to the app directory disappear on every redeploy. To keep balances:
   - Add a **Volume** in Railway mounted at `/data`, and set
     `BOT_DATABASE_PATH=/data/group_dice_royale.db`.
   - Without a volume, all user balances reset on each redeploy.

## First-run migration

On first start with an existing `group_dice_royale.db`, the bot automatically:
- seeds the old BEP20/TRC20 addresses into the new `crypto_wallets` table,
- drops the obsolete UPI column/settings,
- keeps all users, balances, games and transactions.

## Admin panel

- `/admin` → **Crypto Wallet Manager** (add/edit/delete/enable networks),
  **Channel Links** (edit invite links/usernames/logs channel).
- `/backup` (owner, private chat) → download a full DB snapshot.

## Local run

```bash
pip install -r requirements.txt
python casino_royals_bot.py
```
