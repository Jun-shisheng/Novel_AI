"""故事记忆：章节记忆、当前状态、本地 BM25 检索.

设计参考：
- Letta/MemGPT 的分层记忆（核心状态 / 归档章节 / 按需召回）
- GraphRAG/LightRAG 的实体关系与多级摘要思路
- SillyTavern 的 World Info 按需注入
- Pagekin / AI-Novel-Writing-Assistant 的章节状态与本地检索

全部使用 Python 标准库 + SQLite FTS5（不可用时退回纯 Python BM25），
不依赖向量库或嵌入模型。
"""
import json
import math
import re

from database import get_db
from text_chunker import chunk_text
from utils import normalize_newlines

_CJK_RE = re.compile(r"[㐀-䶿一-鿿]+")
_ASCII_RE = re.compile(r"[A-Za-z0-9]+")
_ASCII_STOP = {
    "the", "and", "for", "that", "with", "this", "from", "was", "were",
    "are", "is", "of", "to", "in", "on", "at", "as", "by", "an", "or",
}

# 检索分块比概要分块更细，便于精确召回
_RETRIEVE_CHUNK_CHARS = 1200
_RETRIEVE_OVERLAP_CHARS = 150


def tokenize(text: str) -> list[str]:
    """中文二元组 + 英文字母数字词，零依赖。"""
    text = normalize_newlines(text)
    tokens: list[str] = []
    for run in _CJK_RE.findall(text):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    for word in _ASCII_RE.findall(text):
        word = word.lower()
        if len(word) >= 2 and word not in _ASCII_STOP:
            tokens.append(word)
    return tokens


def _tokens_text(text: str) -> str:
    return " ".join(tokenize(text))


async def _has_fts(db) -> bool:
    cursor = await db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory_fts'"
    )
    return await cursor.fetchone() is not None


async def _delete_fts_rows(db, ids: list[int]) -> None:
    if not ids:
        return
    try:
        if await _has_fts(db):
            for chunk_id in ids:
                await db.execute("DELETE FROM memory_fts WHERE rowid = ?", (chunk_id,))
    except Exception:
        pass


async def _clear_chunks_db(db, doc_path: str) -> None:
    cursor = await db.execute("SELECT id FROM memory_chunks WHERE doc_path = ?", (doc_path,))
    ids = [int(row[0]) for row in await cursor.fetchall()]
    await _delete_fts_rows(db, ids)
    await db.execute("DELETE FROM memory_chunks WHERE doc_path = ?", (doc_path,))


async def _index_text_db(db, doc_path: str, text: str, append: bool) -> int:
    text = normalize_newlines(text)
    if not text.strip():
        return 0
    if not append:
        await _clear_chunks_db(db, doc_path)
        seq_start = 0
    else:
        cursor = await db.execute(
            "SELECT COALESCE(MAX(seq), -1) + 1 FROM memory_chunks WHERE doc_path = ?", (doc_path,)
        )
        row = await cursor.fetchone()
        seq_start = int(row[0] or 0)

    has_fts = await _has_fts(db)
    chunks = chunk_text(text, max_chars=_RETRIEVE_CHUNK_CHARS, overlap_chars=_RETRIEVE_OVERLAP_CHARS)
    for offset, chunk in enumerate(chunks):
        tokens = _tokens_text(chunk)
        if not tokens:
            continue
        cursor = await db.execute(
            "INSERT INTO memory_chunks (doc_path, seq, text, tokens) VALUES (?, ?, ?, ?)",
            (doc_path, seq_start + offset, chunk, tokens),
        )
        chunk_id = int(cursor.lastrowid)
        if has_fts:
            try:
                await db.execute(
                    "INSERT INTO memory_fts (rowid, doc_path, chunk_id, tokens) VALUES (?, ?, ?, ?)",
                    (chunk_id, doc_path, chunk_id, tokens),
                )
            except Exception:
                pass
    return len(chunks)


async def _replace_chapters_db(db, doc_path: str, chapters: list[dict]) -> None:
    await db.execute("DELETE FROM chapter_memory WHERE doc_path = ?", (doc_path,))
    await _insert_chapters_db(db, doc_path, chapters, start_index=1)


async def _insert_chapters_db(
    db, doc_path: str, chapters: list[dict], start_index: int = 1
) -> None:
    for offset, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            continue
        try:
            index = int(chapter.get("chapter_index") or (start_index + offset))
        except (TypeError, ValueError):
            index = start_index + offset
        state = chapter.get("state") or {}
        await db.execute(
            "INSERT OR REPLACE INTO chapter_memory "
            "(doc_path, chapter_index, title, summary, state_json, updated_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (
                doc_path,
                index,
                str(chapter.get("title") or ""),
                str(chapter.get("summary") or ""),
                json.dumps(state, ensure_ascii=False),
            ),
        )


async def _append_chapters_db(db, doc_path: str, chapters: list[dict]) -> None:
    cursor = await db.execute(
        "SELECT COALESCE(MAX(chapter_index), 0) FROM chapter_memory WHERE doc_path = ?",
        (doc_path,),
    )
    row = await cursor.fetchone()
    start = int(row[0] or 0) + 1
    # 增量追加时忽略调用方给的序号，统一从现有最大序号往后排
    relative = [
        {key: value for key, value in chapter.items() if key != "chapter_index"}
        for chapter in chapters
        if isinstance(chapter, dict)
    ]
    await _insert_chapters_db(db, doc_path, relative, start_index=start)


async def _save_state_db(db, doc_path: str, state: dict) -> None:
    await db.execute(
        "INSERT OR REPLACE INTO story_state (doc_path, state_json, updated_at) "
        "VALUES (?, ?, datetime('now'))",
        (doc_path, json.dumps(state or {}, ensure_ascii=False)),
    )


async def replace_memory(doc_path: str, text: str, chapters: list[dict], state: dict) -> None:
    """全量重建：检索索引 + 章节记忆 + 当前状态（同一事务）。"""
    db = await get_db()
    try:
        await _index_text_db(db, doc_path, text, append=False)
        await _replace_chapters_db(db, doc_path, chapters)
        await _save_state_db(db, doc_path, state)
        await db.commit()
    finally:
        await db.close()


async def append_memory(doc_path: str, new_text: str, chapters: list[dict], state: dict) -> None:
    """增量追加：只索引新文本，追加章节记忆并更新当前状态。"""
    db = await get_db()
    try:
        await _index_text_db(db, doc_path, new_text, append=True)
        await _append_chapters_db(db, doc_path, chapters)
        await _save_state_db(db, doc_path, state)
        await db.commit()
    finally:
        await db.close()


async def import_memory(doc_path: str, chapters: list[dict], state: dict) -> None:
    """导入概要时恢复章节记忆与状态；不重建检索索引。"""
    db = await get_db()
    try:
        await _replace_chapters_db(db, doc_path, chapters)
        await _save_state_db(db, doc_path, state)
        await db.commit()
    finally:
        await db.close()


async def clear_memory(doc_path: str) -> None:
    db = await get_db()
    try:
        await _clear_chunks_db(db, doc_path)
        await db.execute("DELETE FROM chapter_memory WHERE doc_path = ?", (doc_path,))
        await db.execute("DELETE FROM story_state WHERE doc_path = ?", (doc_path,))
        await db.commit()
    finally:
        await db.close()


async def rebuild_index(doc_path: str, text: str) -> int:
    """只重建检索索引，不调用 AI。"""
    db = await get_db()
    try:
        count = await _index_text_db(db, doc_path, text, append=False)
        await db.commit()
        return count
    finally:
        await db.close()


async def get_story_state(doc_path: str) -> dict:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT state_json FROM story_state WHERE doc_path = ?", (doc_path,)
        )
        row = await cursor.fetchone()
        if not row:
            return {}
        try:
            state = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return {}
        return state if isinstance(state, dict) else {}
    finally:
        await db.close()


async def get_chapters(doc_path: str, limit: int | None = None) -> list[dict]:
    db = await get_db()
    try:
        if limit and limit > 0:
            cursor = await db.execute(
                "SELECT chapter_index, title, summary, state_json FROM chapter_memory "
                "WHERE doc_path = ? ORDER BY chapter_index DESC LIMIT ?",
                (doc_path, limit),
            )
            rows = list(await cursor.fetchall())
            rows.reverse()
        else:
            cursor = await db.execute(
                "SELECT chapter_index, title, summary, state_json FROM chapter_memory "
                "WHERE doc_path = ? ORDER BY chapter_index ASC",
                (doc_path,),
            )
            rows = await cursor.fetchall()
    finally:
        await db.close()

    chapters = []
    for row in rows:
        try:
            state = json.loads(row["state_json"])
        except (json.JSONDecodeError, TypeError):
            state = {}
        chapters.append({
            "chapter_index": int(row["chapter_index"]),
            "title": str(row["title"] or ""),
            "summary": str(row["summary"] or ""),
            "state": state if isinstance(state, dict) else {},
        })
    return chapters


async def get_memory_raw(doc_path: str) -> dict:
    return {
        "story_state": await get_story_state(doc_path),
        "chapters": await get_chapters(doc_path),
    }


def _is_excluded(text: str, exclude_text: str) -> bool:
    chunk_norm = normalize_newlines(text).strip()
    exclude_norm = normalize_newlines(exclude_text).strip()
    if not chunk_norm or not exclude_norm:
        return False
    if chunk_norm == exclude_norm:
        return True
    if len(exclude_norm) >= 100 and exclude_norm in chunk_norm:
        return True
    if len(chunk_norm) >= 100 and chunk_norm in exclude_norm:
        return True
    return False


async def _search_fallback(db, doc_path: str, query_tokens: list[str], limit: int) -> list[str]:
    cursor = await db.execute(
        "SELECT text, tokens FROM memory_chunks WHERE doc_path = ?", (doc_path,)
    )
    rows = await cursor.fetchall()
    query_set = set(query_tokens)
    scored = []
    for row in rows:
        tokens = set(str(row["tokens"]).split())
        if not tokens:
            continue
        overlap = len(query_set & tokens)
        if not overlap:
            continue
        score = overlap / math.sqrt(len(tokens) + 1)
        scored.append((score, str(row["text"])))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [text for _score, text in scored[:limit]]


async def search(
    doc_path: str,
    query: str,
    top_k: int = 4,
    exclude_text: str = "",
) -> list[str]:
    """本地检索相关前文；零依赖。"""
    if not doc_path or not query.strip() or top_k <= 0:
        return []

    # FTS5 对超长 query 词数敏感，限制唯一词数量
    query_tokens = list(dict.fromkeys(tokenize(query)))[:300]
    if not query_tokens:
        return []

    db = await get_db()
    try:
        results: list[str] = []
        if await _has_fts(db):
            match = " OR ".join(f'"{token}"' for token in query_tokens)
            try:
                cursor = await db.execute(
                    "SELECT chunk_id FROM memory_fts "
                    "WHERE memory_fts MATCH ? AND doc_path = ? "
                    "ORDER BY bm25(memory_fts) LIMIT ?",
                    (match, doc_path, top_k * 4),
                )
                ids = [int(row[0]) for row in await cursor.fetchall()]
                if ids:
                    placeholders = ",".join("?" for _ in ids)
                    cursor = await db.execute(
                        f"SELECT id, text FROM memory_chunks WHERE id IN ({placeholders})",
                        ids,
                    )
                    texts = {int(row["id"]): str(row["text"]) for row in await cursor.fetchall()}
                    results = [texts[i] for i in ids if i in texts]
            except Exception:
                results = []
        if not results:
            results = await _search_fallback(db, doc_path, query_tokens, top_k * 4)
    finally:
        await db.close()

    deduped = []
    seen = set()
    for text in results:
        if _is_excluded(text, exclude_text):
            continue
        key = normalize_newlines(text)[:120]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
        if len(deduped) >= top_k:
            break
    return deduped


async def get_memory(
    doc_path: str,
    query: str = "",
    exclude_text: str = "",
    top_k: int = 4,
    recent_chapters: int = 3,
) -> dict:
    """给润色/续写/改写注入的记忆上下文。"""
    if not doc_path:
        return {}
    state = await get_story_state(doc_path)
    chapters = await get_chapters(doc_path, limit=recent_chapters)
    retrieved = await search(doc_path, query, top_k=top_k, exclude_text=exclude_text)
    if not state and not chapters and not retrieved:
        return {}
    return {
        "story_state": state,
        "recent_chapters": chapters,
        "retrieved": [{"text": text} for text in retrieved],
    }
