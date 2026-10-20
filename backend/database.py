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
    # 章节级记忆：每块正文的概要、结尾状态
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chapter_memory (
            doc_path TEXT NOT NULL,
            chapter_index INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            state_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (doc_path, chapter_index)
        )
    """)
    # 当前故事状态（时间/地点/在场人物/物品/线索/关系）
    await db.execute("""
        CREATE TABLE IF NOT EXISTS story_state (
            doc_path TEXT PRIMARY KEY,
            state_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    # 检索分块（纯本地 BM25/FTS5）
    await db.execute("""
        CREATE TABLE IF NOT EXISTS memory_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_path TEXT NOT NULL,
            seq INTEGER NOT NULL,
            text TEXT NOT NULL,
            tokens TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_chunks_doc ON memory_chunks(doc_path, seq)"
    )
    # FTS5 在 Python 自带 SQLite 中通常可用；不可用时 memory_manager 会退回 Python BM25
    try:
        await db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                doc_path UNINDEXED,
                chunk_id UNINDEXED,
                tokens
            )
        """)
    except Exception:
        pass
    await db.commit()
    return db
