"""请求/响应数据模型."""
from pydantic import BaseModel, Field


class PolishRequest(BaseModel):
    text: str = Field(..., description="选中文本")
    context_before: str = Field("", description="前文")
    context_after: str = Field("", description="后文")
    summary: dict[str, object] = Field(default_factory=dict, description="全局概要")
    style_tags: list[str] = Field(default_factory=list)
    avoid_text: str = Field("", description="上一次生成的内容，避免重复")
    doc_path: str = Field("", description="文档路径，用于加载故事记忆")


class PolishResponse(BaseModel):
    polished_text: str


class RewriteRequest(BaseModel):
    text: str = Field(..., description="选中文本")
    context_before: str = Field("", description="前文")
    context_after: str = Field("", description="后文")
    style: str = Field("更简洁", description="目标风格")
    summary: dict[str, object] = Field(default_factory=dict)
    style_tags: list[str] = Field(default_factory=list)
    avoid_text: str = Field("", description="上一次生成的内容，避免重复")
    doc_path: str = Field("", description="文档路径，用于加载故事记忆")


class ContinueRequest(BaseModel):
    context_before: str = Field(..., description="光标前文")
    context_after: str = Field("", description="光标后文")
    summary: dict[str, object] = Field(default_factory=dict)
    style_tags: list[str] = Field(default_factory=list)
    target_length: int = Field(0, ge=0, le=20000, description="目标字数，0 表示不限")
    avoid_text: str = Field("", description="上一次生成的内容，避免重复")
    doc_path: str = Field("", description="文档路径，用于加载故事记忆")


class OutlineRequest(BaseModel):
    text: str = Field(..., description="全文文本")
    doc_path: str = Field("")
    summary: dict[str, object] = Field(default_factory=dict)
    style_tags: list[str] = Field(default_factory=list)


class OutlineResponse(BaseModel):
    outline: str


class CharacterCardsRequest(BaseModel):
    text: str = Field("", description="正文参考（可为空，仅用概要）")
    doc_path: str = Field("")
    summary: dict[str, object] = Field(default_factory=dict)


class SummaryGenerateRequest(BaseModel):
    text: str = Field(..., description="全文文本")
    doc_path: str = Field("", description="关联的文档路径")
    doc_end: int = Field(0, ge=0, description="Word 文档总字符位置")


class SummaryUpdateRequest(BaseModel):
    new_text: str = Field(..., description="新增文本")
    doc_path: str = Field("")
    doc_end: int = Field(0, ge=0, description="更新后的 Word 文档总字符位置")


class SummarySaveRequest(BaseModel):
    doc_path: str = Field(..., description="关联的文档路径")
    summary: dict[str, object]


class SummaryImportRequest(BaseModel):
    doc_path: str = Field(..., description="关联的文档路径")
    summary: dict[str, object]
    summarized_end: int = Field(0, ge=0)
    story_state: dict[str, object] = Field(default_factory=dict)
    chapters: list[dict[str, object]] = Field(default_factory=list)


class MemoryIndexRequest(BaseModel):
    doc_path: str = Field(..., description="关联的文档路径")
    text: str = Field(..., description="用于重建检索索引的全文")


class ConsistencyCheckRequest(BaseModel):
    text: str = Field(..., description="待检查的生成文本")
    context_before: str = Field("")
    context_after: str = Field("")
    doc_path: str = Field("")
    action: str = Field("", description="润色/改写/续写")


class ConsistencyFixRequest(BaseModel):
    text: str = Field(..., description="待修正文本")
    issues: list[dict[str, object]] = Field(default_factory=list)
    doc_path: str = Field("")


class SummaryDeleteRequest(BaseModel):
    doc_path: str = Field(..., description="关联的文档路径")


class SummaryResponse(BaseModel):
    summary: dict[str, object]


class SummaryListResponse(BaseModel):
    items: list[dict[str, object]]


class StyleTagsResponse(BaseModel):
    tags: list[str]


class DocStateResponse(BaseModel):
    summarized_end: int = 0
    updated_at: str | None = None


class SettingsResponse(BaseModel):
    config: dict[str, object]


class SettingsUpdateRequest(BaseModel):
    config: dict[str, object]


class CancelResponse(BaseModel):
    message: str
