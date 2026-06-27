"""概要 CRUD 与增量更新."""
import json
from database import get_db
from text_chunker import chunk_text
from prompt_builder import build_summary_chunk_prompt, build_summary_merge_prompt
from deepseek_client import chat_completion


async def get_summary(doc_path: str) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT summary_json FROM summaries WHERE doc_path = ?", (doc_path,))
        row = await cursor.fetchone()
        return json.loads(row[0]) if row else None
    finally:
        await db.close()


async def get_style_tags(doc_path: str) -> list[str]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT tags_json FROM style_tags WHERE doc_path = ?", (doc_path,))
        row = await cursor.fetchone()
        return json.loads(row[0]) if row else []
    finally:
        await db.close()


async def generate_summary(text: str, doc_path: str) -> dict:
    """全量生成概要：分块 → 逐块提取 → 合并。"""
    chunks = chunk_text(text)
    extractions = []

    for i, chunk in enumerate(chunks):
        messages = build_summary_chunk_prompt(chunk, is_first=(i == 0))
        result = await chat_completion(messages, temperature=0.3, max_tokens=2048)
        try:
            parsed = json.loads(result.strip().removeprefix("```json").removesuffix("```").strip())
            extractions.append(parsed)
        except json.JSONDecodeError:
            extractions.append({"raw": result})

    # 如果只有一个块，直接返回
    if len(extractions) == 1:
        summary = extractions[0]
    else:
        # 合并多个块的提取结果
        merge_messages = build_summary_merge_prompt({}, extractions)
        merged = await chat_completion(merge_messages, temperature=0.3, max_tokens=4096)
        try:
            summary = json.loads(merged.strip().removeprefix("```json").removesuffix("```").strip())
        except json.JSONDecodeError:
            summary = {"raw_extractions": extractions}

    # 存储
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO summaries (doc_path, summary_json, updated_at) VALUES (?, ?, datetime('now'))",
            (doc_path, json.dumps(summary, ensure_ascii=False)),
        )
        # 提取风格标签
        style_tags = summary.get("风格标签", []) if isinstance(summary, dict) else []
        if style_tags:
            await db.execute(
                "INSERT OR REPLACE INTO style_tags (doc_path, tags_json) VALUES (?, ?)",
                (doc_path, json.dumps(style_tags, ensure_ascii=False)),
            )
        await db.commit()
    finally:
        await db.close()

    return summary


async def update_summary(new_text: str, doc_path: str) -> dict:
    """增量更新概要：从新文本提取 → 与现有概要合并。"""
    existing = await get_summary(doc_path) or {}
    chunks = chunk_text(new_text)
    extractions = []
    for chunk in chunks:
        messages = build_summary_chunk_prompt(chunk, is_first=False)
        result = await chat_completion(messages, temperature=0.3, max_tokens=2048)
        try:
            extractions.append(json.loads(result.strip().removeprefix("```json").removesuffix("```").strip()))
        except json.JSONDecodeError:
            extractions.append({"raw": result})

    merge_messages = build_summary_merge_prompt(existing, extractions)
    merged = await chat_completion(merge_messages, temperature=0.3, max_tokens=4096)
    try:
        summary = json.loads(merged.strip().removeprefix("```json").removesuffix("```").strip())
    except json.JSONDecodeError:
        summary = {"existing": existing, "new_extractions": extractions}

    db = await get_db()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO summaries (doc_path, summary_json, updated_at) VALUES (?, ?, datetime('now'))",
            (doc_path, json.dumps(summary, ensure_ascii=False)),
        )
        style_tags = summary.get("风格标签", []) if isinstance(summary, dict) else []
        if style_tags:
            await db.execute(
                "INSERT OR REPLACE INTO style_tags (doc_path, tags_json) VALUES (?, ?)",
                (doc_path, json.dumps(style_tags, ensure_ascii=False)),
            )
        await db.commit()
    finally:
        await db.close()

    return summary
