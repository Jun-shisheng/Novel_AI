"""SQLite 初始化与连接管理."""
import aiosqlite
from pathlib import Path

DB_DIR = Path(__file__).parent.parent / ".ai-writing"
DB_DIR.mkdir(parents=True, exist_ok=True)


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(str(DB_DIR / "summaries.db"))
    db.row_factory = aiosqlite.Row
    # 后台服务与启动器可能同时访问，避免偶发 database is locked
    await db.execute("PRAGMA busy_timeout = 5000")
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
    # 记录概要覆盖到文档的哪个字符位置，供增量自动更新使用
    await db.execute("""
        CREATE TABLE IF NOT EXISTS doc_state (
            doc_path TEXT PRIMARY KEY,
            summarized_end INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    await db.commit()
    return db
