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
    ticket_type   TEXT    NOT NULL DEFAULT 'pending',
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

CREATE TABLE IF NOT EXISTS purchases (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    product_name  TEXT    NOT NULL,
    purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        
        # Migração segura: adiciona a coluna se o banco já existia antes
        try:
            await db.execute("ALTER TABLE tickets ADD COLUMN ticket_type TEXT NOT NULL DEFAULT 'pending'")
            await db.commit()
        except aiosqlite.OperationalError:
            pass # A coluna já existe, ignora o erro

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

async def set_ticket_type(channel_id: int, t_type: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tickets SET ticket_type = ? WHERE channel_id = ?",
            (t_type, channel_id),
        )
        await db.commit()

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

# ─── FUNÇÕES PARA O ADMIN TOOLS ──────────────────────────────

async def get_user_tickets(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM tickets WHERE user_id = ? ORDER BY id DESC", 
            (user_id,)
        )
        return await cur.fetchall()

async def get_user_messages(user_id: int, limit: int = 50):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM messages WHERE author_id = ? ORDER BY id DESC LIMIT ?", 
            (user_id, limit)
        )
        return await cur.fetchall()

async def add_purchase(user_id: int, product_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO purchases (user_id, product_name) VALUES (?, ?)",
            (user_id, product_name)
        )
        await db.commit()

async def get_user_purchases(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM purchases WHERE user_id = ? ORDER BY id DESC",
            (user_id,)
        )
        return await cur.fetchall()

async def get_total_purchases() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM purchases")
        row = await cur.fetchone()
        return row[0] if row else 0
