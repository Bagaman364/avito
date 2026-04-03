import aiosqlite
from config import DATABASE_PATH


async def init_db() -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS members (
                telegram_id  INTEGER PRIMARY KEY,
                username     TEXT,
                added_by     INTEGER,
                added_at     TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS avito_accounts (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                name             TEXT NOT NULL,
                client_id        TEXT NOT NULL,
                client_secret    TEXT NOT NULL,
                access_token     TEXT,
                token_expires_at INTEGER DEFAULT 0,
                avito_user_id    TEXT,
                avito_phone      TEXT,
                added_by         INTEGER
            );

            CREATE TABLE IF NOT EXISTS processed_messages (
                message_id TEXT PRIMARY KEY,
                processed_at TEXT DEFAULT (datetime('now'))
            );
        """)
        await db.commit()


# ── Members ──────────────────────────────────────────────────────────────────

async def add_member(telegram_id: int, username: str, added_by: int) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO members (telegram_id, username, added_by) VALUES (?, ?, ?)",
            (telegram_id, username, added_by),
        )
        await db.commit()


async def remove_member(telegram_id: int) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "DELETE FROM members WHERE telegram_id = ?", (telegram_id,)
        )
        await db.commit()
        return cur.rowcount > 0


async def get_all_members() -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM members ORDER BY added_at")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def is_member(telegram_id: int) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT 1 FROM members WHERE telegram_id = ?", (telegram_id,)
        )
        return await cur.fetchone() is not None


async def get_member_by_username(username: str) -> dict | None:
    username = username.lstrip("@").lower()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM members WHERE lower(username) = ?", (username,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


# ── Avito accounts ────────────────────────────────────────────────────────────

async def add_avito_account(
    name: str,
    client_id: str,
    client_secret: str,
    added_by: int,
) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            """INSERT INTO avito_accounts (name, client_id, client_secret, added_by)
               VALUES (?, ?, ?, ?)""",
            (name, client_id, client_secret, added_by),
        )
        await db.commit()
        return cur.lastrowid


async def update_account_token(
    account_id: int,
    access_token: str,
    expires_at: int,
    avito_user_id: str,
    avito_phone: str,
) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """UPDATE avito_accounts
               SET access_token=?, token_expires_at=?, avito_user_id=?, avito_phone=?
               WHERE id=?""",
            (access_token, expires_at, avito_user_id, avito_phone, account_id),
        )
        await db.commit()


async def update_account_name(account_id: int, name: str) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE avito_accounts SET name=? WHERE id=?", (name, account_id)
        )
        await db.commit()


async def delete_avito_account(account_id: int) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "DELETE FROM avito_accounts WHERE id=?", (account_id,)
        )
        await db.commit()
        return cur.rowcount > 0


async def get_all_avito_accounts() -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM avito_accounts ORDER BY id")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_avito_account(account_id: int) -> dict | None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM avito_accounts WHERE id=?", (account_id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


# ── Processed messages ────────────────────────────────────────────────────────

async def is_message_processed(message_id: str) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT 1 FROM processed_messages WHERE message_id=?", (message_id,)
        )
        return await cur.fetchone() is not None


async def mark_message_processed(message_id: str) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO processed_messages (message_id) VALUES (?)",
            (message_id,),
        )
        await db.commit()


async def cleanup_old_processed(days: int = 30) -> None:
    """Remove records older than `days` days to keep the table small."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "DELETE FROM processed_messages WHERE processed_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        await db.commit()
