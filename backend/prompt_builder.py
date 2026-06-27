"""Prompt 模板和概要注入."""
import json


def build_polish_prompt(text: str, context_before: str, context_after: str, summary: dict, style_tags: list[str]) -> list[dict]:
    style_str = ", ".join(style_tags) if style_tags else "与上下文一致"
    summary_json = json.dumps(summary, ensure_ascii=False, indent=2) if summary else "（暂无概要）"

    system = (
        "你是一位专业的小说编辑，擅长优化文字表达、丰富细节，同时严格保持作者的原意和风格。\n"
        "规则：\n"
        "1. 扩写原文，使其更生动、更具画面感，增加约 {expand}% 的长度\n"
        "2. 必须保留所有对话、专有名词、人名地名\n"
        "3. 不改变情节走向，不添加新事件\n"
        "4. 不改变人称和视角\n"
        "5. 直接输出润色后的文本，不要加任何解释或标记\n"
        f"风格参考：{style_str}"
    ).format(expand=30)

    user = (
        f"## 前文（保持连贯）\n{context_before}\n\n"
        f"## 待润色段落\n{text}\n\n"
        f"## 后文（保持连贯）\n{context_after}\n\n"
        f"## 作品概要\n{summary_json}\n\n"
        "请输出润色扩写后的完整段落，直接替换原文："
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_continue_prompt(context_before: str, context_after: str, summary: dict, style_tags: list[str]) -> list[dict]:
    style_str = ", ".join(style_tags) if style_tags else "与上下文一致"
    summary_json = json.dumps(summary, ensure_ascii=False, indent=2) if summary else "（暂无概要）"

    system = (
        "你是一位专业的小说作家，擅长根据上下文无缝续写。\n"
        "规则：\n"
        "1. 严格保持原文的人称、视角和叙事风格\n"
        "2. 推进情节合理发展，与全局概要保持一致\n"
        "3. 保持对话风格、节奏感与原文一致\n"
        "4. 不要重复已有内容，从光标处自然延续\n"
        "5. 直接输出续写文本，不要加解释\n"
        f"风格：{style_str}"
    )

    user = (
        f"## 前文（从光标往前）\n{context_before}\n\n"
        f"## 后文（光标之后的内容，避免矛盾）\n{context_after}\n\n"
        f"## 作品概要\n{summary_json}\n\n"
        "请从光标位置自然续写："
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_summary_chunk_prompt(chunk_text: str, is_first: bool) -> list[dict]:
    """分块提取概要的 prompt。"""
    if is_first:
        user = (
            "请从以下小说片段中提取结构化信息，以 JSON 格式输出：\n\n"
            f"{chunk_text}\n\n"
            "输出格式：\n"
            '{"主角": {"姓名": "", "当前状态": "", "目标": "", "冲突": ""}, '
            '"情节线": "", '
            '"人物": [{"姓名": "", "角色": "", "与其他人物关系": ""}], '
            '"伏笔": [], '
            '"世界观元素": [], '
            '"风格标签": []}'
        )
    else:
        user = (
            "以下是追加的小说片段，请提取新增信息，以相同 JSON 格式输出（只输出新增/更新部分）：\n\n"
            f"{chunk_text}"
        )
    return [
        {"role": "system", "content": "你是一位专业的小说分析编辑，擅长提取小说中的结构化元信息。"},
        {"role": "user", "content": user},
    ]


def build_summary_merge_prompt(existing_summary: dict, new_extractions: list[dict]) -> list[dict]:
    """合并多个分块概要的 prompt。"""
    existing_json = json.dumps(existing_summary, ensure_ascii=False, indent=2) if existing_summary else "{}"
    new_json = json.dumps(new_extractions, ensure_ascii=False, indent=2)
    return [
        {
            "role": "system",
            "content": "你是一位专业的小说分析编辑。将现有概要与新提取的信息合并，去重、更新、整合，输出完整的合并后 JSON。",
        },
        {
            "role": "user",
            "content": f"现有概要：\n{existing_json}\n\n新提取信息（按顺序）：\n{new_json}\n\n请输出合并后的完整概要 JSON：",
        },
    ]
