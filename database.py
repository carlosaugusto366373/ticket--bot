import aiosqlite
from pathlib import Path

DB_PATH = Path("storage/tickets.db")
DB_PATH.parent.mkdir(exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id    INTEGER UNIQUE NOT NULL,
    user_id       INTEGER NOT NULL,
    category      TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'open',
    claimed_by    INTEGER,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at     TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id   INTEGER NOT NULL,
    author_id   INTEGER NOT NULL,
    is_bot      INTEGER NOT NULL DEFAULT 0,
    content     TEXT    NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
);
"""

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()

async def create_ticket(channel_id: int, user_id: int, category: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO tickets (channel_id, user_id, category) VALUES (?, ?, ?)",
            (channel_id, user_id, category),
        )
        await db.commit()
        return cur.lastrowid

async def get_ticket_by_channel(channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM tickets WHERE channel_id = ?", (channel_id,)
        )
        return await cur.fetchone()

async def claim_ticket(channel_id: int, staff_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tickets SET claimed_by = ?, status = 'claimed' WHERE channel_id = ?",
            (staff_id, channel_id),
        )
        await db.commit()

async def close_ticket(channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tickets SET status = 'closed', closed_at = CURRENT_TIMESTAMP "
            "WHERE channel_id = ?",
            (channel_id,),
        )
        await db.commit()

async def log_message(ticket_id: int, author_id: int, content: str, is_bot: bool = False):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (ticket_id, author_id, is_bot, content) "
            "VALUES (?, ?, ?, ?)",
            (ticket_id, author_id, int(is_bot), content),
        )
        await db.commit()

async def get_history(ticket_id: int, limit: int = 20):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM messages WHERE ticket_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (ticket_id, limit),
        )
        rows = await cur.fetchall()
        return list(reversed(rows))

async def get_all_messages(ticket_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM messages WHERE ticket_id = ? ORDER BY id ASC",
            (ticket_id,),
        )
        return await cur.fetchall()