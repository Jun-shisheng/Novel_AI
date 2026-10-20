"""Word AI 写作助手 — Python 后台入口."""
import asyncio
import logging
import uuid

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from config import load_config, save_config
from models import (
    PolishRequest, PolishResponse,
    RewriteRequest,
    ContinueRequest,
    OutlineRequest, OutlineResponse, CharacterCardsRequest,
    SummaryGenerateRequest, SummaryUpdateRequest, SummarySaveRequest,
    SummaryImportRequest, SummaryDeleteRequest, SummaryResponse, SummaryListResponse,
    StyleTagsResponse, DocStateResponse,
    MemoryIndexRequest, ConsistencyCheckRequest, ConsistencyFixRequest,
    SettingsResponse, SettingsUpdateRequest,
    CancelResponse,
)
from deepseek_client import chat_completion, chat_completion_stream
from prompt_builder import build_polish_prompt, build_rewrite_prompt, build_continue_prompt
from summary_manager import (
    get_summary, get_style_tags, get_doc_state,
    generate_summary, update_summary, save_summary, import_summary,
    delete_summary, list_summaries, generate_outline, generate_character_cards,
    check_consistency, fix_consistency,
)
import memory_manager
from cancel_manager import cancel_manager
from version import __version__

app = FastAPI(title="Word AI Writing Assistant", version=__version__)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _upstream_error(exc: Exception) -> str:
    """把上游错误转换成用户能看懂的提示（不泄露 Key）。"""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        detail = ""
        try:
            payload = exc.response.json()
            if isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, dict):
                    detail = str(error.get("message") or "")
                elif error:
                    detail = str(error)
                detail = detail or str(payload.get("message") or "")
        except Exception:
            try:
                detail = exc.response.text[:300]
            except Exception:
                detail = ""
        if status == 401:
            return "API Key 无效或未配置，请按 Ctrl+Alt+K 重新设置"
        if status == 402:
            return "账户余额不足，请检查 DeepSeek 账户"
        if status == 429:
            return "请求过于频繁或额度不足，请稍后重试"
        suffix = f"：{detail}" if detail else ""
        return f"AI 服务返回错误 ({status}){suffix}"
    if isinstance(exc, httpx.RequestError):
        return f"无法连接 AI 服务：{exc}"
    return f"AI 请求失败：{exc}"


async def _run_ai(coro):
    try:
        return await coro
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        raise HTTPException(status_code=502, detail=_upstream_error(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI 请求失败：{exc}") from exc


async def _load_memory(
    doc_path: str,
    query: str,
    exclude_text: str = "",
    top_k: int | None = None,
) -> dict:
    cfg = load_config()
    if not doc_path or not cfg.get("memory_enabled", True):
        return {}
    try:
        return await memory_manager.get_memory(
            doc_path,
            query=query,
            exclude_text=exclude_text,
            top_k=top_k if top_k is not None else int(cfg.get("memory_retrieve_top_k", 4)),
            recent_chapters=int(cfg.get("memory_recent_chapters", 3)),
        )
    except Exception:
        logging.getLogger("main").exception("加载故事记忆失败")
        return {}


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": __version__}


@app.post("/api/polish", response_model=PolishResponse)
async def polish(req: PolishRequest):
    cfg = load_config()
    memory = await _load_memory(
        req.doc_path,
        query=req.context_before[-1200:] + "\n" + req.text + "\n" + req.context_after[:400],
        exclude_text=req.text,
    )
    messages = build_polish_prompt(
        req.text, req.context_before, req.context_after,
        req.summary, req.style_tags,
        expand_ratio=cfg.get("polish_expand_ratio", 1.3),
        avoid_text=req.avoid_text,
        memory=memory,
    )
    result = await _run_ai(chat_completion(messages, temperature=0.9, max_tokens=4096))
    return PolishResponse(polished_text=result)


@app.post("/api/rewrite", response_model=PolishResponse)
async def rewrite(req: RewriteRequest):
    memory = await _load_memory(
        req.doc_path,
        query=req.context_before[-1200:] + "\n" + req.text + "\n" + req.context_after[:400],
        exclude_text=req.text,
    )
    messages = build_rewrite_prompt(
        req.text, req.context_before, req.context_after,
        req.summary, req.style_tags, req.style,
        avoid_text=req.avoid_text,
        memory=memory,
    )
    result = await _run_ai(chat_completion(messages, temperature=0.9, max_tokens=4096))
    return PolishResponse(polished_text=result)


@app.post("/api/continue")
async def continue_write(req: ContinueRequest):
    session_id = uuid.uuid4().hex[:8]
    cancel_event = cancel_manager.create(session_id)
    memory = await _load_memory(
        req.doc_path,
        query=req.context_before[-1800:] + "\n" + req.context_after[:500],
        # 已经在上下文里的近期原文不再重复注入，检索更早的相关段落
        exclude_text=req.context_before[-3000:] + "\n" + req.context_after[:500],
    )
    messages = build_continue_prompt(
        req.context_before, req.context_after,
        req.summary, req.style_tags, req.target_length, req.avoid_text,
        memory=memory,
    )

    async def event_generator():
        generated = 0
        try:
            yield {"event": "session", "data": session_id}
            async for chunk in chat_completion_stream(messages, cancel_event=cancel_event):
                yield {"event": "chunk", "data": chunk}
                generated += len(chunk)
                if req.target_length and generated >= req.target_length:
                    cancel_event.set()
                    break
            yield {"event": "done", "data": ""}
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            yield {"event": "error", "data": _upstream_error(exc)}
        finally:
            cancel_manager.remove(session_id)

    return EventSourceResponse(event_generator())


@app.post("/api/stop", response_model=CancelResponse)
async def stop(session_id: str = ""):
    if not session_id:
        count = cancel_manager.cancel_all()
        return CancelResponse(message=f"已停止 {count} 个续写会话")
    if cancel_manager.cancel(session_id):
        return CancelResponse(message=f"续写 {session_id} 已停止")
    return CancelResponse(message="未找到活跃续写会话")


@app.post("/api/outline", response_model=OutlineResponse)
async def outline(req: OutlineRequest):
    text = await _run_ai(generate_outline(req.text, req.summary, req.style_tags))
    return OutlineResponse(outline=text)


@app.post("/api/characters", response_model=SummaryResponse)
async def character_cards(req: CharacterCardsRequest):
    cards = await _run_ai(generate_character_cards(req.text, req.summary))
    return SummaryResponse(summary=cards)


@app.get("/api/memory/get")
async def memory_get(doc_path: str = ""):
    return await memory_manager.get_memory_raw(doc_path or "default")


@app.post("/api/memory/index")
async def memory_index(req: MemoryIndexRequest):
    count = await memory_manager.rebuild_index(req.doc_path or "default", req.text)
    return {"chunks": count}


@app.post("/api/consistency/check")
async def consistency_check(req: ConsistencyCheckRequest):
    summary = await get_summary(req.doc_path or "default") if req.doc_path else {}
    return await _run_ai(
        check_consistency(
            req.text, req.context_before, req.context_after,
            summary or {}, req.doc_path, req.action,
        )
    )


@app.post("/api/consistency/fix")
async def consistency_fix(req: ConsistencyFixRequest):
    summary = await get_summary(req.doc_path or "default") if req.doc_path else {}
    fixed = await _run_ai(
        fix_consistency(req.text, req.issues, summary or {}, req.doc_path)
    )
    return {"fixed_text": fixed}


@app.post("/api/summary/generate", response_model=SummaryResponse)
async def summary_generate(req: SummaryGenerateRequest):
    summary = await _run_ai(generate_summary(req.text, req.doc_path or "default", req.doc_end))
    return SummaryResponse(summary=summary)


@app.post("/api/summary/update", response_model=SummaryResponse)
async def summary_update(req: SummaryUpdateRequest):
    summary = await _run_ai(update_summary(req.new_text, req.doc_path or "default", req.doc_end))
    return SummaryResponse(summary=summary)


@app.get("/api/summary/get", response_model=SummaryResponse)
async def summary_get(doc_path: str = ""):
    summary = await get_summary(doc_path or "default")
    return SummaryResponse(summary=summary or {})


@app.get("/api/summary/list", response_model=SummaryListResponse)
async def summary_list():
    return SummaryListResponse(items=await list_summaries())


@app.get("/api/summary/state", response_model=DocStateResponse)
async def summary_state(doc_path: str = ""):
    state = await get_doc_state(doc_path or "default")
    if not state:
        return DocStateResponse(summarized_end=0)
    return DocStateResponse(**state)


@app.post("/api/summary/save", response_model=SummaryResponse)
async def summary_save(req: SummarySaveRequest):
    summary = await _run_ai(save_summary(req.doc_path or "default", req.summary))
    return SummaryResponse(summary=summary)


@app.post("/api/summary/import", response_model=SummaryResponse)
async def summary_import(req: SummaryImportRequest):
    summary = await _run_ai(
        import_summary(
            req.doc_path or "default",
            req.summary,
            req.summarized_end,
            req.story_state,
            req.chapters,
        )
    )
    return SummaryResponse(summary=summary)


@app.post("/api/summary/delete")
async def summary_delete(req: SummaryDeleteRequest):
    await delete_summary(req.doc_path or "default")
    return {"status": "ok"}


@app.get("/api/style_tags", response_model=StyleTagsResponse)
async def style_tags_get(doc_path: str = ""):
    return StyleTagsResponse(tags=await get_style_tags(doc_path or "default"))


@app.get("/api/settings", response_model=SettingsResponse)
async def settings_get():
    return SettingsResponse(config=load_config())


@app.post("/api/settings")
async def settings_update(req: SettingsUpdateRequest):
    save_config(req.config)
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=19800)
