from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PDFPagePreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)
    text: str
    cleaned_text: str


class PDFProcessingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    page_count: int = Field(ge=1)
    pages: list[PDFPagePreview]
    text: str
    has_extractable_text: bool


class PDFIngestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    filename: str
    source_type: str = "pdf"
    source_path: str
    page_count: int = Field(ge=1)
    chunk_count: int = Field(ge=0)
    status: str
    embedding_status: str | None = Field(
        default=None,
        description="completed, failed or not_configured. Only an embedded document is searchable by the assistant.",
    )
    embedding_model: str | None = Field(default=None, description="The model that embedded the chunks.")


class PDFPreviewError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class ImageIngestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    filename: str
    source_type: str = "image"
    source_path: str
    chunk_count: int = Field(ge=1)
    ocr_line_count: int = Field(ge=1)
    ocr_mean_confidence: float = Field(ge=0.0, le=1.0)
    embedding_status: str = Field(description="completed, failed or not_configured; only embedded text is searchable.")
    status: str = "processed"
