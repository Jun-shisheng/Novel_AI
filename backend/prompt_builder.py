"""Prompt 模板和概要注入."""
import json


def _summary_json(summary: dict) -> str:
    return json.dumps(summary, ensure_ascii=False, indent=2) if summary else "（暂无概要）"


def _style_str(style_tags: list[str]) -> str:
    return ", ".join(style_tags) if style_tags else "与上下文一致"


def build_polish_prompt(
    text: str,
    context_before: str,
    context_after: str,
    summary: dict,
    style_tags: list[str],
    expand_ratio: float = 1.3,
) -> list[dict]:
    try:
        percent = round((float(expand_ratio) - 1) * 100)
    except (TypeError, ValueError):
        percent = 30
    percent = max(0, min(percent, 200))

    system = (
        "你是一位专业的小说编辑，擅长优化文字表达、丰富细节，同时严格保持作者的原意和风格。\n"
        "规则：\n"
        f"1. 扩写原文，使其更生动、更具画面感，增加约 {percent}% 的长度\n"
        "2. 必须保留所有对话、专有名词、人名地名\n"
        "3. 不改变情节走向，不添加新事件\n"
        "4. 不改变人称和视角\n"
        "5. 直接输出润色后的文本，不要加任何解释或标记\n"
        "6. 段落之间不要增加空行，保持原文的段落间距格式\n"
        f"风格参考：{_style_str(style_tags)}"
    )

    user = (
        f"## 前文（保持连贯）\n{context_before}\n\n"
        f"## 待润色段落\n{text}\n\n"
        f"## 后文（保持连贯）\n{context_after}\n\n"
        f"## 作品概要\n{_summary_json(summary)}\n\n"
        "请输出润色扩写后的完整段落，直接替换原文："
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_rewrite_prompt(
    text: str,
    context_before: str,
    context_after: str,
    summary: dict,
    style_tags: list[str],
    style: str,
) -> list[dict]:
    system = (
        "你是一位专业的小说编辑，擅长按照指定风格改写文字。\n"
        "规则：\n"
        "1. 严格保留原文的情节、信息、对话内容、专有名词、人名地名\n"
        "2. 不增加或删除事件，不改变人称、视角和叙事顺序\n"
        "3. 只改变语言风格与表达方式，长度与原文接近\n"
        "4. 直接输出改写后的文本，不要加任何解释、标题或标记\n"
        "5. 段落之间不要增加空行\n"
        f"作品原有风格参考：{_style_str(style_tags)}"
    )
    user = (
        f"## 目标风格\n{style}\n\n"
        f"## 前文（保持连贯）\n{context_before}\n\n"
        f"## 待改写段落\n{text}\n\n"
        f"## 后文（保持连贯）\n{context_after}\n\n"
        f"## 作品概要\n{_summary_json(summary)}\n\n"
        "请输出改写后的完整段落，直接替换原文："
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_continue_prompt(
    context_before: str,
    context_after: str,
    summary: dict,
    style_tags: list[str],
    target_length: int = 0,
) -> list[dict]:
    system = (
        "你是一位专业的小说作家，擅长根据上下文无缝续写。\n"
        "规则：\n"
        "1. 严格保持原文的人称、视角和叙事风格\n"
        "2. 推进情节合理发展，与全局概要保持一致\n"
        "3. 保持对话风格、节奏感与原文一致\n"
        "4. 不要重复已有内容，从光标处自然延续\n"
        "5. 合理分段，段落之间用一个空行分隔（即两个换行符）\n"
        "6. 直接输出续写文本，不要加解释"
    )
    if target_length:
        system += f"\n7. 本次续写目标约 {target_length} 字，达到目标后自然收束，不要无限续写"
    system += f"\n风格：{_style_str(style_tags)}"

    user = (
        f"## 前文（从光标往前）\n{context_before}\n\n"
        f"## 后文（光标之后的内容，避免矛盾）\n{context_after}\n\n"
        f"## 作品概要\n{_summary_json(summary)}\n\n"
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
            '{"主角": {"姓名": "", "梗概": "", "当前状态": "", "目标": "", "冲突": "", "后续发展": ""}, '
            '"情节线": "", '
            '"人物": [{"姓名": "", "角色": "", "人物梗概": "", "与其他人物关系": "", "后续发展": ""}], '
            '"角色关系": [{"角色A": "", "角色B": "", "关系": "", "发展": ""}], '
            '"伏笔": [], '
            '"世界观元素": [], '
            '"风格标签": []}'
        )
    else:
        user = (
            "以下是追加的小说片段，请提取新增信息，以相同 JSON 格式输出（只输出新增/更新部分，不要输出解释）：\n\n"
            f"{chunk_text}"
        )
    return [
        {"role": "system", "content": "你是一位专业的小说分析编辑，擅长提取小说中的结构化元信息。只输出 JSON。"},
        {"role": "user", "content": user},
    ]


def build_summary_merge_prompt(existing_summary: dict, new_extractions: list[dict]) -> list[dict]:
    """合并多个分块概要的 prompt。"""
    existing_json = json.dumps(existing_summary, ensure_ascii=False, indent=2) if existing_summary else "{}"
    new_json = json.dumps(new_extractions, ensure_ascii=False, indent=2)
    return [
        {
            "role": "system",
            "content": (
                "你是一位专业的小说分析编辑。将现有概要与新提取的信息合并，去重、更新、整合，"
                "输出完整的合并后 JSON（保持原有字段结构），只输出 JSON，不要解释。"
            ),
        },
        {
            "role": "user",
            "content": f"现有概要：\n{existing_json}\n\n新提取信息（按顺序）：\n{new_json}\n\n请输出合并后的完整概要 JSON：",
        },
    ]


def build_outline_prompt(text: str, summary: dict, style_tags: list[str]) -> list[dict]:
    system = (
        "你是一位专业的小说编辑，擅长梳理章节结构。\n"
        "请根据作品概要和正文，输出 Markdown 格式的章节大纲。\n"
        "要求：\n"
        "1. 按剧情顺序划分章节，每章列出：标题、核心事件、出场人物、伏笔/悬念\n"
        "2. 忠于原文，不虚构未发生的情节\n"
        "3. 如果原文已有章节标题，沿用原顺序\n"
        "4. 直接输出大纲，不要添加解释"
    )
    user = (
        f"## 作品概要\n{_summary_json(summary)}\n\n"
        f"## 风格标签\n{_style_str(style_tags)}\n\n"
        f"## 正文\n{text}\n\n"
        "请输出章节大纲："
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_outline_chunk_prompt(chunk_text: str, summary: dict) -> list[dict]:
    system = (
        "你是一位专业的小说编辑。请从以下正文片段中提取剧情要点，"
        "按顺序列出事件、出场人物和伏笔，每条一行，不要虚构。"
    )
    user = (
        f"## 已有作品概要\n{_summary_json(summary)}\n\n"
        f"## 正文片段\n{chunk_text}\n\n"
        "请输出这段正文的剧情要点："
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_character_card_prompt(summary: dict, text: str) -> list[dict]:
    """生成/完善角色卡：梗概、关系、后续发展。"""
    system = (
        "你是一位专业的小说编辑，擅长梳理人物设定与人物弧光。\n"
        "请基于作品概要和正文，生成结构化的角色卡。\n"
        "要求：\n"
        "1. 主角和重要人物都要覆盖，不要遗漏正文中出现的重要配角\n"
        "2. 每个人物包含：梗概（身份与经历）、当前状态、目标、冲突、与其他人物关系、后续发展\n"
        "3. 关系要写清双向关系与变化，例如「师徒 → 决裂 → 和解」\n"
        "4. 后续发展只基于原文已有伏笔和趋势做合理推断，不要凭空虚构新事件\n"
        "5. 只输出 JSON，不要解释\n"
        "输出格式：\n"
        '{"主角": {"姓名": "", "梗概": "", "当前状态": "", "目标": "", "冲突": "", "后续发展": ""}, '
        '"人物": [{"姓名": "", "角色": "", "人物梗概": "", "当前状态": "", "目标": "", '
        '"与其他人物关系": "", "后续发展": ""}], '
        '"角色关系": [{"角色A": "", "角色B": "", "关系": "", "发展": ""}]}'
    )
    user = (
        f"## 现有作品概要\n{_summary_json(summary)}\n\n"
        f"## 正文参考\n{text}\n\n"
        "请输出完善后的角色卡 JSON："
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_outline_merge_prompt(parts: list[str], summary: dict) -> list[dict]:
    system = (
        "你是一位专业的小说编辑。请把分段剧情要点整合为 Markdown 章节大纲，"
        "按剧情顺序划分章节，每章列出：标题、核心事件、出场人物、伏笔/悬念。"
        "忠于原文，不虚构，直接输出大纲。"
    )
    body = "\n\n".join(f"### 片段 {i + 1}\n{part}" for i, part in enumerate(parts))
    user = f"## 作品概要\n{_summary_json(summary)}\n\n## 分段剧情要点\n{body}\n\n请输出完整章节大纲："
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
