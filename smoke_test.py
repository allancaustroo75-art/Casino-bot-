# -*- coding: utf-8 -*-
"""Smoke test for the modified casino bot: migration + wallet manager + deposits/withdrawals."""
import os
import shutil
import sqlite3
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

WORK = Path(tempfile.mkdtemp(prefix="casino_test_"))

# 1) Build a LEGACY database exactly as the old bot would have created it.
legacy_path = WORK / "legacy.db"
conn = sqlite3.connect(legacy_path)
conn.executescript(
    """
    CREATE TABLE users (
        user_id INTEGER PRIMARY KEY, username TEXT, balance REAL NOT NULL DEFAULT 0,
        wins INTEGER NOT NULL DEFAULT 0, losses INTEGER NOT NULL DEFAULT 0,
        games INTEGER NOT NULL DEFAULT 0, join_date TEXT NOT NULL,
        first_name TEXT NOT NULL DEFAULT '', join_prompt_sent INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE games (id INTEGER PRIMARY KEY AUTOINCREMENT, player1_id INTEGER NOT NULL,
        player2_id INTEGER NOT NULL, bet REAL NOT NULL, dice_count INTEGER NOT NULL DEFAULT 0,
        p1_rolls TEXT, p2_rolls TEXT, winner_id INTEGER, commission REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL, created_at TEXT NOT NULL, completed_at TEXT,
        p1_dice_count INTEGER, p2_dice_count INTEGER, chat_id INTEGER,
        commission_percent REAL NOT NULL DEFAULT 5, game_type TEXT NOT NULL DEFAULT 'dice',
        p1_message_ids TEXT, p2_message_ids TEXT,
        fairness_source TEXT NOT NULL DEFAULT 'telegram_user_dice',
        display_currency TEXT NOT NULL DEFAULT 'COIN', display_bet REAL, conversion_rate REAL,
        failure_reason TEXT, game_mode TEXT NOT NULL DEFAULT 'pvp');
    CREATE TABLE transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        amount REAL NOT NULL, type TEXT NOT NULL, description TEXT NOT NULL,
        txn_id TEXT, timestamp TEXT NOT NULL);
    CREATE TABLE deposits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        amount REAL NOT NULL, txn_id TEXT NOT NULL, screenshot_id TEXT NOT NULL,
        status TEXT NOT NULL, timestamp TEXT NOT NULL, coin_amount REAL, rate REAL,
        screenshot_type TEXT NOT NULL DEFAULT 'photo', reviewed_at TEXT, reviewed_by INTEGER,
        currency TEXT NOT NULL DEFAULT 'INR', network TEXT, tx_hash TEXT, wallet_address TEXT);
    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE pending_challenges (id INTEGER PRIMARY KEY AUTOINCREMENT,
        challenger_id INTEGER NOT NULL, opponent_id INTEGER NOT NULL, bet REAL NOT NULL,
        dice_count INTEGER NOT NULL DEFAULT 0, timestamp TEXT NOT NULL, chat_id INTEGER,
        message_id INTEGER, status TEXT NOT NULL DEFAULT 'pending', challenger_dice INTEGER,
        opponent_dice INTEGER, game_id INTEGER, accepted_at TEXT,
        commission_percent REAL NOT NULL DEFAULT 5, updated_at TEXT,
        game_type TEXT NOT NULL DEFAULT 'dice', challenger_ready INTEGER NOT NULL DEFAULT 0,
        opponent_ready INTEGER NOT NULL DEFAULT 0, display_currency TEXT NOT NULL DEFAULT 'COIN',
        display_bet REAL, conversion_rate REAL, failure_reason TEXT, game_mode TEXT NOT NULL DEFAULT 'pvp');
    CREATE TABLE feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        game_id INTEGER, rating INTEGER, category TEXT NOT NULL, message TEXT,
        status TEXT NOT NULL DEFAULT 'open', timestamp TEXT NOT NULL,
        resolved_by INTEGER, resolved_at TEXT);
    CREATE TABLE banned_users (user_id INTEGER PRIMARY KEY, reason TEXT NOT NULL,
        banned_by INTEGER NOT NULL, timestamp TEXT NOT NULL);
    CREATE TABLE withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        amount REAL NOT NULL, upi_id TEXT NOT NULL, rate REAL NOT NULL, fiat_amount REAL NOT NULL,
        status TEXT NOT NULL, timestamp TEXT NOT NULL, completed_at TEXT, reviewed_by INTEGER,
        txn_id TEXT, payout_currency TEXT NOT NULL DEFAULT 'INR', payout_amount REAL,
        network TEXT, destination TEXT, proof_file_id TEXT, proof_type TEXT);
    INSERT INTO settings(key, value) VALUES
        ('upi_id', 'owner@okaxis'),
        ('usdt_bep20_address', '0xCustomMigratedBep20Address1234567890abcdef'),
        ('usdt_trc20_address', 'TCustomMigratedTrc20Address0987654321fedcba'),
        ('coin_rate', '1'), ('min_usdt_deposit', '0.10'), ('usdt_inr_rate', '98');
    INSERT INTO withdrawals (user_id, amount, upi_id, rate, fiat_amount, status, timestamp)
        VALUES (111, 50, 'player@upi', 1, 50, 'completed', '2025-01-01T00:00:00Z');
    INSERT INTO deposits (user_id, amount, txn_id, screenshot_id, status, timestamp, currency, network, tx_hash)
        VALUES (222, 1.5, 'DEP-OLD-1', 'shot1', 'approved', '2025-01-01T00:00:00Z', 'USDT', 'trc20', 'a'*64);
    """
)
conn.commit()
conn.close()
print("legacy DB created")

# 2) Point the bot at the legacy DB and import the module (runs migration).
os.environ["BOT_DATABASE_PATH"] = str(legacy_path)
os.environ["BOT_ADMIN_IDS"] = "7984167671"
sys.path.insert(0, "/home/user")
import casino_royals_bot as bot  # noqa: E402

DB = bot.DB
print("module imported; DB path:", DB.path)

# --- Migration checks -----------------------------------------------------
cols = {row[1] for row in sqlite3.connect(legacy_path).execute("PRAGMA table_info(withdrawals)")}
assert "upi_id" not in cols, "upi_id column was not dropped!"
print("PASS: withdrawals.upi_id column dropped")

settings = DB.get_settings()
assert "upi_id" not in settings and "usdt_bep20_address" not in settings, "old settings remain"
print("PASS: obsolete settings purged")

wallets = DB.list_crypto_wallets()
assert len(wallets) == 2, f"expected 2 seeded wallets, got {len(wallets)}"
by_key = {w["network_key"]: w for w in wallets}
assert by_key["bep20"]["wallet_address"] == "0xCustomMigratedBep20Address1234567890abcdef"
assert by_key["trc20"]["wallet_address"] == "TCustomMigratedTrc20Address0987654321fedcba"
assert int(by_key["bep20"]["enabled"]) == 1
print("PASS: legacy wallets seeded from custom admin settings, enabled")

old_wd = DB.get_withdrawal(1)
assert old_wd is not None and old_wd["status"] == "completed"
print("PASS: existing withdrawal rows preserved:", old_wd["amount"], old_wd["destination"])

# --- Wallet manager CRUD ---------------------------------------------------
created = DB.create_crypto_wallet(
    "btc", "Bitcoin", "BTC", "bc1qtestwalletaddress1234567890abcdef",
    "Send only BTC (SegWit).", True,
)
wid = int(created["id"])
assert created["network_key"] == "btc" and int(created["enabled"]) == 1
print("PASS: BTC wallet created, id", wid)

updated = DB.update_crypto_wallet(wid, display_name="Bitcoin (BTC)", enabled=0)
assert int(updated["enabled"]) == 0 and updated["display_name"] == "Bitcoin (BTC)"
print("PASS: wallet updated (name + disabled)")

enabled_list = DB.list_crypto_wallets(True)
assert all(int(w["enabled"]) == 1 for w in enabled_list) and len(enabled_list) == 2
print("PASS: enabled_only filter works, users see only enabled networks")

fetched = DB.get_crypto_wallet(wid)
assert fetched["coin_symbol"] == "BTC"
assert DB.get_crypto_wallet_by_key("btc")["id"] == wid
print("PASS: get_crypto_wallet / get_crypto_wallet_by_key")

# duplicate network key must fail
try:
    DB.create_crypto_wallet("btc", "Bitcoin2", "BTC", "abc1234567890", "", True)
    raise SystemExit("FAIL: duplicate key accepted")
except bot.GameError:
    print("PASS: duplicate network key rejected")

# delete
DB.delete_crypto_wallet(wid)
assert DB.get_crypto_wallet(wid) is None
print("PASS: wallet deleted")

# delete missing -> GameError
try:
    DB.delete_crypto_wallet(99999)
    raise SystemExit("FAIL: deleting missing wallet accepted")
except bot.GameError:
    print("PASS: deleting missing wallet rejected")

# --- Deposit flow (data layer) ---------------------------------------------
rate = Decimal("98")
user_id = 333
dep = DB.create_deposit(
    user_id, Decimal("0.5"), bot.coins_from_usdt(Decimal("0.5"), rate), rate,
    "shot_crypto_1", "photo", "USDT", "trc20", "f" * 64, by_key["trc20"]["wallet_address"],
)
assert dep["currency"] == "USDT" and dep["network"] == "trc20" and dep["status"] == "pending"
print("PASS: USDT deposit row created:", dep["txn_id"])

btc_dep = DB.create_deposit(
    user_id, Decimal("0.01"), Decimal("0.98"), rate,
    "shot_crypto_2", "photo", "BTC", "btc", "g" * 64, "bc1q...",
)
assert btc_dep["currency"] == "BTC" and btc_dep["network"] == "btc"
print("PASS: BTC deposit row created (any enabled/legacy network label)")

try:
    DB.create_deposit(user_id, Decimal("1"), Decimal("98"), rate, "shot3", "photo")
    raise SystemExit("FAIL: deposit without network/tx_hash accepted")
except bot.GameError:
    print("PASS: crypto deposit without network/hash rejected")

# --- Withdrawal flow (data layer) ------------------------------------------
DB.ensure_user(user_id, "smoketester", "Smoke Tester")
DB.admin_credit(user_id, Decimal("100"), 7984167671)
wd = DB.create_withdrawal(user_id, Decimal("49"), "0xReceivingAddress1234567890", rate, Decimal("0.5"), "bep20")
assert wd["payout_currency"] == "USDT" and wd["destination"] == "0xReceivingAddress1234567890"
assert wd["network"] == "bep20" and wd["status"] == "pending"
print("PASS: crypto withdrawal created:", wd["txn_id"] if wd.get("txn_id") else wd["id"])

try:
    DB.create_withdrawal(user_id, Decimal("10"), "0xAddr", rate, Decimal("0.1"), None)
    raise SystemExit("FAIL: withdrawal without network accepted")
except bot.GameError:
    print("PASS: withdrawal without network rejected")

# --- Helper checks ----------------------------------------------------------
assert bot.normalize_crypto_tx_hash("https://explorer.io/tx/" + "a" * 64) == "a" * 64
assert bot.normalize_crypto_tx_hash("0x" + "b" * 64) == "0x" + "b" * 64
assert bot.normalize_crypto_tx_hash("c" * 88) == "c" * 88  # SOL-style base58 length
try:
    bot.normalize_crypto_tx_hash("not-a-hash!!")
    raise SystemExit("FAIL: junk tx hash accepted")
except bot.GameError:
    print("PASS: tx hash validation (explorer links, 0x hex, hex, base58)")

assert bot.validate_crypto_address("  0xAbCdEf1234567890AbCdEf1234567890AbCdEf123  ") == "0xAbCdEf1234567890AbCdEf1234567890AbCdEf123"
assert bot.normalize_currency("usdt") == "USDT" and bot.normalize_currency("coins") == "COIN"
try:
    bot.normalize_currency("inr")
    raise SystemExit("FAIL: INR alias still accepted")
except bot.GameError:
    print("PASS: INR currency alias removed; address/currency validation OK")

# --- QR generation still works for wallet addresses -------------------------
png = bot.make_qr_png(by_key["trc20"]["wallet_address"])
assert png[:8] == b"\x89PNG\r\n\x1a\n"
print("PASS: QR PNG generation from wallet address:", len(png), "bytes")

# --- keyboards reference only real symbols ----------------------------------
kb = bot.network_selection_keyboard(DB.list_crypto_wallets(True), "dep:net")
rows = kb.to_dict()["inline_keyboard"]
assert len(rows) == 2 and all("dep:net:" in btn["callback_data"] for row in rows for btn in row)
kb2 = bot.wallet_manager_keyboard(DB.list_crypto_wallets())
print("PASS: network_selection_keyboard / wallet_manager_keyboard build OK")

# --- build_application wiring -------------------------------------------------
app = bot.build_application()
handlers = app.handlers
flat = []
for group in handlers.values():
    for h in group:
        flat.append(type(h).__name__)
joined = " | ".join(flat)
assert "ConversationHandler" in joined
print("PASS: build_application wired:", joined[:120], "...")

# --- refresh_runtime_configuration still works (sub-admins) -------------------
bot.refresh_runtime_configuration()
assert 7984167671 in bot.ADMIN_IDS
print("PASS: refresh_runtime_configuration")

# --- /backup: consistent snapshot via the online backup API ------------------
import tempfile as _tmp
backup_path = os.path.join(_tmp.gettempdir(), "smoke_backup_test.db")
if os.path.exists(backup_path):
    os.remove(backup_path)
DB.backup_to(backup_path)
assert os.path.exists(backup_path) and os.path.getsize(backup_path) > 0
with sqlite3.connect(backup_path) as bc:
    tables = {r[0] for r in bc.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"crypto_wallets", "users", "deposits", "withdrawals", "settings"} <= tables
    count = bc.execute("SELECT COUNT(*) FROM crypto_wallets").fetchone()[0]
    assert count == 2, f"backup wallet count {count}"
os.remove(backup_path)
print("PASS: backup_to creates a readable, complete snapshot")

# /backup is registered in build_application
backup_registered = any(
    "backup" in (getattr(h, "commands", ()) or ())
    for h in app.handlers.get(0, [])
)
assert backup_registered, "/backup not registered in build_application"
print("PASS: /backup registered in build_application")

# --- Channel & link settings (admin-configurable) ---------------------------
settings = DB.get_settings()
assert settings["required_chat_invite_link"] == "https://t.me/+qtXzPr9VyzIzMWZl"
assert settings["logs_channel_id"] == "-1004476890059"
assert settings["official_channel_username"] == "@CasinoRoyaIs"
print("PASS: channel settings seeded with defaults in DB")

# changing a setting + refresh updates the module globals instantly
DB.set_setting("optional_channel_invite_link", "https://t.me/NewChannel")
DB.set_setting("logs_channel_id", "-1009998887777")
bot.refresh_channel_configuration()
assert bot.OPTIONAL_CHANNEL_INVITE_LINK == "https://t.me/NewChannel"
assert bot.LOGS_CHANNEL_ID == -1009998887777
print("PASS: refresh_channel_configuration applies changes instantly (no restart)")

# invalid logs channel id is ignored safely
DB.set_setting("logs_channel_id", "not-a-number")
bot.refresh_channel_configuration()
assert bot.LOGS_CHANNEL_ID == -1009998887777  # unchanged
print("PASS: invalid logs_channel_id ignored safely")

# clearing a link hides the button instead of sending an empty URL
DB.set_setting("optional_channel_invite_link", "")
bot.refresh_channel_configuration()
assert bot.OPTIONAL_CHANNEL_INVITE_LINK == ""
kb = bot.dashboard_keyboard(7984167671)
rows = kb.to_dict()["inline_keyboard"]
flat = [btn["text"] for row in rows for btn in row]
assert "Join Channel (Optional)" not in flat, "empty-link button must not render"
assert "Join Gaming Group (Optional)" in flat
mkb = bot.membership_keyboard()
flat_m = [btn["text"] for row in mkb.to_dict()["inline_keyboard"] for btn in row]
assert "Join News Channel (Optional)" not in flat_m
print("PASS: cleared links hide their buttons on dashboard/membership keyboards")

# validation rules
assert bot.validate_channel_setting("required_chat_invite_link", "https://t.me/+abc") is None
assert bot.validate_channel_setting("required_chat_invite_link", "http://evil.com") is not None
assert bot.validate_channel_setting("official_channel_username", "@X") is None
assert bot.validate_channel_setting("logs_channel_id", "-100123") is None
assert bot.validate_channel_setting("logs_channel_id", "abc") is not None
print("PASS: channel setting validation (links, usernames, channel id)")

# channel edit conversation registered
channel_conversation = any(
    isinstance(h, bot.ConversationHandler)
    and any(
        "admin:ch:edit:" in str(getattr(ep, "pattern", ""))
        for ep in h.entry_points
    )
    for h in app.handlers.get(0, [])
)
assert channel_conversation, "channel conversation not registered"
print("PASS: channel edit conversation registered in build_application")

print("\nALL SMOKE TESTS PASSED ✔")
