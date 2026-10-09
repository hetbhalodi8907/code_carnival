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


class PDFPreviewError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
