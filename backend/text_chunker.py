"""长文本智能分块，按段落边界切分，尽量不截断句子."""
from utils import normalize_newlines


def _split_long_paragraph(para: str, max_chars: int) -> list[str]:
    """单个段落超过 max_chars 时按句子边界硬切（找不到句子边界时按长度切）。"""
    if len(para) <= max_chars:
        return [para]

    pieces: list[str] = []
    rest = para
    while len(rest) > max_chars:
        window = rest[:max_chars]
        cut = max(window.rfind(ch) for ch in "。！？!?；;…\n")
        # 太靠前就退回按长度切，避免产生过短的块
        if cut < max_chars // 2:
            cut = max_chars
        else:
            cut += 1
        pieces.append(rest[:cut])
        rest = rest[cut:]
    if rest:
        pieces.append(rest)
    return pieces


def chunk_text(text: str, max_chars: int = 8000, overlap_chars: int = 500) -> list[str]:
    """将长文本按段落边界切分为多个块，块间有少量重叠以保持上下文连贯。

    Word 文档使用 \\r 作为段落分隔，这里会先统一为 \\n，避免整篇文档被当成
    一个段落而无法分块。
    """
    text = normalize_newlines(text)
    if not text.strip():
        return []
    if len(text) <= max_chars:
        return [text]

    max_chars = max(1000, max_chars)
    overlap_chars = max(0, min(overlap_chars, max_chars // 4))

    paragraphs = text.split("\n")
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for para in paragraphs:
        for piece in _split_long_paragraph(para, max_chars):
            piece_len = len(piece)
            # 预留一个换行符
            if current_parts and current_len + 1 + piece_len > max_chars:
                chunk = "\n".join(current_parts)
                chunks.append(chunk)
                if overlap_chars:
                    overlap = chunk[-overlap_chars:]
                    current_parts = [overlap, piece]
                    current_len = len(overlap) + 1 + piece_len
                else:
                    current_parts = [piece]
                    current_len = piece_len
            else:
                if current_parts:
                    current_len += 1
                current_parts.append(piece)
                current_len += piece_len

    if current_parts:
        tail = "\n".join(current_parts)
        # 最后一块太短则并入前一块，避免无效的额外 API 调用
        if chunks and len(tail) < 200:
            chunks[-1] = chunks[-1] + "\n" + tail
        elif tail.strip():
            chunks.append(tail)

    return chunks
