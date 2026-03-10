from datetime import datetime

from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    document_id: str
    tenant_id: str
    project_id: str
    filename: str
    document_type: str
    storage_uri: str
    checksum: str
    mime_type: str | None
    status: str
    ingested_at: datetime


class DocumentExtractionRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    extraction_mode: str = Field(default="ocr", min_length=1)


class DocumentExtractionResponse(BaseModel):
    extraction_id: str
    source_document_id: str
    status: str
    provider: str
    quality_score: float | None
    extracted_text_uri: str | None
    raw_payload_uri: str | None
    chunk_count: int


class DocumentExtractionEnqueueResponse(BaseModel):
    extraction_id: str
    source_document_id: str
    status: str
    queue_job_id: str


class DocumentExtractionStatusResponse(BaseModel):
    extraction_id: str
    source_document_id: str
    status: str
    provider: str
    extraction_mode: str
    quality_score: float | None
    chunk_count: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None


class DocumentIndexStatusResponse(BaseModel):
    extraction_id: str
    source_document_id: str
    status: str
    index_provider: str
    index_name: str
    indexed_chunk_count: int
    error_message: str | None
