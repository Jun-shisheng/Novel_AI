"""通用文本与 JSON 处理工具."""
import json
import re


def normalize_newlines(text: str) -> str:
    """把 Word 的 \\r、Windows 的 \\r\\n 统一成 \\n。"""
    return str(text).replace("\r\n", "\n").replace("\r", "\n")


def extract_json(text: str):
    """从 LLM 回复中提取 JSON。

    兼容 ```json 代码块、前后夹带解释文字、JSON 前后有空白等情况。
    解析失败时抛出 ValueError。
    """
    if text is None:
        raise ValueError("AI 返回内容为空")
    raw = str(text).strip()
    if not raw:
        raise ValueError("AI 返回内容为空")

    # 去掉 Markdown 代码围栏（可能带 json 标记）
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 从混杂文本中截取第一个完整的 JSON 对象/数组
    starts = [(raw.find("{"), "{"), (raw.find("["), "[")]
    starts = [(pos, ch) for pos, ch in starts if pos != -1]
    if starts:
        pos, ch = min(starts, key=lambda item: item[0])
        close = "}" if ch == "{" else "]"
        end = raw.rfind(close)
        if end > pos:
            try:
                return json.loads(raw[pos:end + 1])
            except json.JSONDecodeError:
                pass

    raise ValueError("AI 返回内容不是有效 JSON")
