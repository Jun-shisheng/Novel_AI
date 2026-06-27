"""请求/响应数据模型."""
from pydantic import BaseModel, Field


class PolishRequest(BaseModel):
    text: str = Field(..., description="选中文本")
    context_before: str = Field("", description="前文")
    context_after: str = Field("", description="后文")
    summary: dict[str, object] = Field(default_factory=dict, description="全局概要")
    style_tags: list[str] = Field(default_factory=list)


class PolishResponse(BaseModel):
    polished_text: str


class ContinueRequest(BaseModel):
    context_before: str = Field(..., description="光标前文")
    context_after: str = Field("", description="光标后文")
    summary: dict[str, object] = Field(default_factory=dict)
    style_tags: list[str] = Field(default_factory=list)


class SummaryGenerateRequest(BaseModel):
    text: str = Field(..., description="全文文本")
    doc_path: str = Field("", description="关联的文档路径")


class SummaryUpdateRequest(BaseModel):
    new_text: str = Field(..., description="新增文本")
    doc_path: str = Field("")


class SummaryResponse(BaseModel):
    summary: dict[str, object]


class SettingsResponse(BaseModel):
    config: dict[str, object]


class SettingsUpdateRequest(BaseModel):
    config: dict[str, object]


class CancelResponse(BaseModel):
    message: str
