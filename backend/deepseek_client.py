"""DeepSeek API 客户端，兼容 OpenAI SDK 格式."""
import json
from typing import AsyncGenerator
import httpx
from config import load_config


def _get_client() -> tuple[str, str, str, httpx.AsyncClient]:
    cfg = load_config()
    api_key = cfg["api_key"]
    base_url = cfg["api_base_url"].rstrip("/")
    model = cfg["model"]
    client = httpx.AsyncClient(
        base_url=base_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout=httpx.Timeout(120.0),
    )
    return api_key, base_url, model, client


async def chat_completion(messages: list[dict], temperature: float = 0.7, max_tokens: int = 4096) -> str:
    """非流式请求，返回完整响应文本。"""
    _, _, model, client = _get_client()
    try:
        resp = await client.post(
            "/chat/completions",
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    finally:
        await client.aclose()


async def chat_completion_stream(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    cancel_event=None,
) -> AsyncGenerator[str, None]:
    """流式请求，yield 每个 chunk 的 delta content。cancel_event 为 asyncio.Event 时支持取消。"""
    _, _, model, client = _get_client()
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
                if cancel_event and cancel_event.is_set():
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
