"""概要 CRUD、增量更新与作品库管理."""
import json
import re
from pathlib import Path

from database import get_db
from text_chunker import chunk_text
from prompt_builder import (
    build_summary_chunk_prompt,
    build_summary_merge_prompt,
    build_outline_prompt,
    build_outline_chunk_prompt,
    build_outline_merge_prompt,
    build_character_card_prompt,
)
from deepseek_client import chat_completion
from utils import extract_json, normalize_newlines


def _coerce_tags(summary: dict) -> list[str]:
    tags = summary.get("风格标签", []) if isinstance(summary, dict) else []
    if isinstance(tags, str):
        tags = re.split(r"[,，、;；/]", tags)
    if not isinstance(tags, (list, tuple, set)):
        return []
    return [str(tag).strip() for tag in tags if str(tag).strip()]


def _as_summary_dict(value) -> dict:
    return value if isinstance(value, dict) else {"raw_extractions": value}


async def _save_summary_row(db, doc_path: str, summary: dict) -> None:
    await db.execute(
        "INSERT OR REPLACE INTO summaries (doc_path, summary_json, updated_at) VALUES (?, ?, datetime('now'))",
        (doc_path, json.dumps(summary, ensure_ascii=False)),
    )
    await db.execute(
        "INSERT OR REPLACE INTO style_tags (doc_path, tags_json) VALUES (?, ?)",
        (doc_path, json.dumps(_coerce_tags(summary), ensure_ascii=False)),
    )


async def _set_doc_end(db, doc_path: str, summarized_end: int) -> None:
    await db.execute(
        "INSERT OR REPLACE INTO doc_state (doc_path, summarized_end, updated_at) "
        "VALUES (?, ?, datetime('now'))",
        (doc_path, max(0, int(summarized_end))),
    )


async def get_summary(doc_path: str) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT summary_json FROM summaries WHERE doc_path = ?", (doc_path,))
        row = await cursor.fetchone()
        if not row:
            return None
        try:
            value = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return None
        return value if isinstance(value, dict) else {"raw_extractions": value}
    finally:
        await db.close()


async def get_style_tags(doc_path: str) -> list[str]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT tags_json FROM style_tags WHERE doc_path = ?", (doc_path,))
        row = await cursor.fetchone()
        if not row:
            return []
        try:
            tags = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return []
        return [str(tag) for tag in tags] if isinstance(tags, list) else []
    finally:
        await db.close()


async def get_doc_state(doc_path: str) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT summarized_end, updated_at FROM doc_state WHERE doc_path = ?", (doc_path,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {"summarized_end": int(row[0] or 0), "updated_at": row[1]}
    finally:
        await db.close()


async def generate_summary(text: str, doc_path: str, doc_end: int = 0) -> dict:
    """全量生成概要：分块 → 逐块提取 → 合并。"""
    text = normalize_newlines(text)
    if not text.strip():
        raise ValueError("文档为空，无法生成概要")

    chunks = chunk_text(text)
    extractions = []

    for i, chunk in enumerate(chunks):
        messages = build_summary_chunk_prompt(chunk, is_first=(i == 0))
        result = await chat_completion(messages, temperature=0.3, max_tokens=2048)
        try:
            extractions.append(extract_json(result))
        except ValueError:
            extractions.append({"raw": result})

    if len(extractions) == 1:
        summary = _as_summary_dict(extractions[0])
    elif extractions:
        merge_messages = build_summary_merge_prompt({}, extractions)
        merged = await chat_completion(merge_messages, temperature=0.3, max_tokens=4096)
        try:
            summary = _as_summary_dict(extract_json(merged))
        except ValueError:
            summary = {"raw_extractions": extractions}
    else:
        raise ValueError("文档为空，无法生成概要")

    db = await get_db()
    try:
        await _save_summary_row(db, doc_path, summary)
        if doc_end > 0:
            await _set_doc_end(db, doc_path, doc_end)
        await db.commit()
    finally:
        await db.close()

    return summary


async def update_summary(new_text: str, doc_path: str, doc_end: int = 0) -> dict:
    """增量更新概要：从新文本提取 → 与现有概要合并。"""
    existing = await get_summary(doc_path)
    new_text = normalize_newlines(new_text)
    if not new_text.strip():
        return existing or {}
    if not existing:
        # 没有旧概要时，把本次文本当作全文处理
        return await generate_summary(new_text, doc_path, doc_end)

    chunks = chunk_text(new_text)
    extractions = []
    for chunk in chunks:
        messages = build_summary_chunk_prompt(chunk, is_first=False)
        result = await chat_completion(messages, temperature=0.3, max_tokens=2048)
        try:
            extractions.append(extract_json(result))
        except ValueError:
            extractions.append({"raw": result})

    if not extractions:
        return existing

    merge_messages = build_summary_merge_prompt(existing, extractions)
    merged = await chat_completion(merge_messages, temperature=0.3, max_tokens=4096)
    try:
        summary = _as_summary_dict(extract_json(merged))
    except ValueError:
        summary = dict(existing)

    # 合并结果缺少风格标签时保留旧标签
    if not _coerce_tags(summary) and _coerce_tags(existing):
        summary["风格标签"] = existing["风格标签"]

    db = await get_db()
    try:
        await _save_summary_row(db, doc_path, summary)
        if doc_end > 0:
            await _set_doc_end(db, doc_path, doc_end)
        await db.commit()
    finally:
        await db.close()

    return summary


async def save_summary(doc_path: str, summary: dict) -> dict:
    """手动保存编辑后的概要（保留已覆盖位置）。"""
    if not isinstance(summary, dict):
        raise ValueError("概要必须是 JSON 对象")
    db = await get_db()
    try:
        await _save_summary_row(db, doc_path, summary)
        await db.commit()
    finally:
        await db.close()
    return summary


async def import_summary(doc_path: str, summary: dict, summarized_end: int = 0) -> dict:
    """导入概要；summarized_end 为导入文件记录的覆盖位置。"""
    if not isinstance(summary, dict):
        raise ValueError("概要必须是 JSON 对象")
    db = await get_db()
    try:
        await _save_summary_row(db, doc_path, summary)
        await _set_doc_end(db, doc_path, summarized_end)
        await db.commit()
    finally:
        await db.close()
    return summary


async def delete_summary(doc_path: str) -> None:
    db = await get_db()
    try:
        await db.execute("DELETE FROM summaries WHERE doc_path = ?", (doc_path,))
        await db.execute("DELETE FROM style_tags WHERE doc_path = ?", (doc_path,))
        await db.execute("DELETE FROM doc_state WHERE doc_path = ?", (doc_path,))
        await db.commit()
    finally:
        await db.close()


async def list_summaries() -> list[dict]:
    """作品库列表：文档路径、标题、主角、风格标签、已覆盖位置、更新时间。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            SELECT s.doc_path, s.summary_json, s.updated_at,
                   COALESCE(t.tags_json, '[]') AS tags_json,
                   COALESCE(d.summarized_end, 0) AS summarized_end
            FROM summaries s
            LEFT JOIN style_tags t ON t.doc_path = s.doc_path
            LEFT JOIN doc_state d ON d.doc_path = s.doc_path
            ORDER BY s.updated_at DESC
            """
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()

    items = []
    for row in rows:
        doc_path = row["doc_path"]
        try:
            summary = json.loads(row["summary_json"])
        except (json.JSONDecodeError, TypeError):
            summary = {}
        if not isinstance(summary, dict):
            summary = {}

        try:
            tags = json.loads(row["tags_json"])
        except (json.JSONDecodeError, TypeError):
            tags = []
        if not isinstance(tags, list):
            tags = []

        main = summary.get("主角", {})
        main_name = main.get("姓名", "") if isinstance(main, dict) else ""
        fallback = Path(doc_path).stem if doc_path not in ("", "default") else "未命名文档"
        title = summary.get("标题") or fallback

        items.append({
            "doc_path": doc_path,
            "title": str(title),
            "main_character": str(main_name or ""),
            "style_tags": [str(tag) for tag in tags],
            "summarized_end": int(row["summarized_end"] or 0),
            "updated_at": str(row["updated_at"] or ""),
        })
    return items


async def generate_character_cards(text: str, summary: dict) -> dict:
    """基于概要和正文生成角色卡（梗概、关系、后续发展）。"""
    text = normalize_newlines(text)
    summary = summary if isinstance(summary, dict) else {}
    if not text.strip() and not summary:
        raise ValueError("没有可用的概要和正文，请先按 Ctrl+Shift+G 生成概要")

    # 角色弧光更依赖开头设定和最新剧情，长文只取首尾
    if len(text) > 20000:
        text = text[:8000] + "\n\n……（中间内容省略）……\n\n" + text[-12000:]

    messages = build_character_card_prompt(summary, text)
    result = await chat_completion(messages, temperature=0.3, max_tokens=4096)
    cards = extract_json(result)
    if not isinstance(cards, dict):
        raise ValueError("AI 返回的角色卡格式不正确")
    return cards


async def generate_outline(text: str, summary: dict, style_tags: list[str]) -> str:
    """生成章节大纲。短文档一次完成，长文档分段提取后合并。"""
    text = normalize_newlines(text)
    if not text.strip():
        raise ValueError("文档为空，无法生成大纲")

    if len(text) <= 12000:
        messages = build_outline_prompt(text, summary, style_tags)
        return await chat_completion(messages, temperature=0.4, max_tokens=4096)

    parts = []
    for chunk in chunk_text(text, max_chars=8000, overlap_chars=200):
        result = await chat_completion(
            build_outline_chunk_prompt(chunk, summary), temperature=0.3, max_tokens=1500
        )
        if result.strip():
            parts.append(result.strip())

    if not parts:
        return ""
    merged = await chat_completion(
        build_outline_merge_prompt(parts, summary), temperature=0.4, max_tokens=4096
    )
    return merged
