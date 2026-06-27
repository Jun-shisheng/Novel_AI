"""长文本智能分块，按段落边界切分，尽量不截断句子."""


def chunk_text(text: str, max_chars: int = 8000, overlap_chars: int = 500) -> list[str]:
    """将长文本按段落边界切分为多个块，块间有重叠以保持上下文连贯。"""
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n")
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 1 <= max_chars:
            current = (current + "\n" + para).strip()
        else:
            if current:
                chunks.append(current)
            # 重叠：保留上一块的末尾
            overlap = current[-overlap_chars:] if len(current) > overlap_chars else current
            current = (overlap + "\n" + para).strip() if overlap else para

    if current.strip():
        # 如果最后一块太短（<200字），合并到前一块
        if len(chunks) > 0 and len(current) < 200:
            chunks[-1] = chunks[-1] + "\n" + current
        else:
            chunks.append(current)

    return chunks
