"""DeepSeek API 客户端，兼容 OpenAI SDK 格式."""
import asyncio
import json
from typing import AsyncGenerator

import httpx

from config import load_config


def _get_client(timeout: float = 120.0) -> tuple[str, str, httpx.AsyncClient]:
    cfg = load_config()
    api_key = str(cfg.get("api_key") or "").strip()
    if not api_key:
        raise ValueError("未配置 DeepSeek API Key，请在 Word 中按 Ctrl+Alt+K 设置")
    base_url = str(cfg.get("api_base_url") or "https://api.deepseek.com/v1").rstrip("/")
    model = str(cfg.get("model") or "deepseek-chat")
    client = httpx.AsyncClient(
        base_url=base_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout=httpx.Timeout(timeout, connect=15.0),
    )
    return model, base_url, client


async def _post_with_retry(client: httpx.AsyncClient, payload: dict, retries: int = 2) -> httpx.Response:
    """对网络错误、429 和 5xx 做有限重试；4xx（如 Key 无效）立即返回。"""
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await client.post("/chat/completions", json=payload)
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_error = exc
            if attempt >= retries:
                raise
            await asyncio.sleep(1.0 * (attempt + 1))
            continue

        if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
            await resp.aclose()
            await asyncio.sleep(1.0 * (attempt + 1))
            continue

        resp.raise_for_status()
        return resp

    raise last_error or RuntimeError("AI 请求失败")


async def chat_completion(
    messages: list[dict], temperature: float = 0.7, max_tokens: int = 4096, timeout: float = 120.0
) -> str:
    """非流式请求，返回完整响应文本。"""
    model, _, client = _get_client(timeout=timeout)
    try:
        resp = await _post_with_retry(
            client,
            {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            },
        )
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    finally:
        await client.aclose()


async def chat_completion_stream(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    cancel_event=None,
    timeout: float = 180.0,
) -> AsyncGenerator[str, None]:
    """流式请求，yield 每个 chunk 的 delta content。cancel_event 为 asyncio.Event 时支持取消。"""
    if cancel_event is not None and cancel_event.is_set():
        return

    model, _, client = _get_client(timeout=timeout)
    try:
        async with client.stream(
            "POST",
            "/chat/completions",
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if cancel_event is not None and cancel_event.is_set():
                    break
                if line.startswith("data: "):
                    chunk = line[6:]
                    if chunk == "[DONE]":
                        break
                    try:
                        delta = json.loads(chunk)["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
    finally:
        await client.aclose()
