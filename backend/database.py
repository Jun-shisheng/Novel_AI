"""SQLite 初始化与连接管理."""
import aiosqlite
from pathlib import Path

DB_DIR = Path("G:/WordAI/.ai-writing")
DB_DIR.mkdir(parents=True, exist_ok=True)


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(str(DB_DIR / "summaries.db"))
    db.row_factory = aiosqlite.Row
    await db.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            doc_path TEXT PRIMARY KEY,
            summary_json TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS style_tags (
            doc_path TEXT PRIMARY KEY,
            tags_json TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY (doc_path) REFERENCES summaries(doc_path)
        )
    """)
    await db.commit()
    return db
