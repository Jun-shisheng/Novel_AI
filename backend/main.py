"""Word AI 写作助手 — Python 后台入口."""
import uuid
import json
import asyncio
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from config import load_config, save_config
from models import (
    PolishRequest, PolishResponse,
    ContinueRequest,
    SummaryGenerateRequest, SummaryUpdateRequest, SummaryResponse,
    SettingsResponse, SettingsUpdateRequest,
    CancelResponse,
)
from deepseek_client import chat_completion, chat_completion_stream
from prompt_builder import build_polish_prompt, build_continue_prompt
from summary_manager import get_summary, get_style_tags, generate_summary, update_summary
from cancel_manager import cancel_manager

app = FastAPI(title="Word AI Writing Assistant")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/polish", response_model=PolishResponse)
async def polish(req: PolishRequest):
    messages = build_polish_prompt(
        req.text, req.context_before, req.context_after,
        req.summary, req.style_tags,
    )
    result = await chat_completion(messages, temperature=0.7, max_tokens=4096)
    return PolishResponse(polished_text=result)


@app.post("/api/continue")
async def continue_write(req: ContinueRequest):
    session_id = uuid.uuid4().hex[:8]
    cancel_event = cancel_manager.create(session_id)
    messages = build_continue_prompt(
        req.context_before, req.context_after,
        req.summary, req.style_tags,
    )

    async def event_generator():
        try:
            yield {"event": "session", "data": session_id}
            async for chunk in chat_completion_stream(messages, cancel_event=cancel_event):
                yield {"event": "chunk", "data": chunk}
            yield {"event": "done", "data": ""}
        except asyncio.CancelledError:
            yield {"event": "cancelled", "data": ""}
        finally:
            cancel_manager.remove(session_id)

    return EventSourceResponse(event_generator())


@app.post("/api/stop", response_model=CancelResponse)
async def stop(session_id: str = ""):
    if not session_id:
        # 取消所有活跃会话
        for sid in list(cancel_manager._events.keys()):
            cancel_manager.cancel(sid)
        return CancelResponse(message="所有续写已停止")
    if cancel_manager.cancel(session_id):
        return CancelResponse(message=f"续写 {session_id} 已停止")
    return CancelResponse(message="未找到活跃续写会话")


@app.post("/api/summary/generate", response_model=SummaryResponse)
async def summary_generate(req: SummaryGenerateRequest):
    summary = await generate_summary(req.text, req.doc_path or "default")
    return SummaryResponse(summary=summary)


@app.post("/api/summary/update", response_model=SummaryResponse)
async def summary_update(req: SummaryUpdateRequest):
    summary = await update_summary(req.new_text, req.doc_path or "default")
    return SummaryResponse(summary=summary)


@app.get("/api/summary/get", response_model=SummaryResponse)
async def summary_get(doc_path: str = ""):
    summary = await get_summary(doc_path or "default")
    return SummaryResponse(summary=summary or {})


@app.get("/api/settings", response_model=SettingsResponse)
async def settings_get():
    return SettingsResponse(config=load_config())


@app.post("/api/settings")
async def settings_update(req: SettingsUpdateRequest):
    save_config(req.config)
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=19800)
