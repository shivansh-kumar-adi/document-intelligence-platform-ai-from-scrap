from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)


class CollectionUpdate(CollectionCreate):
    pass


class CollectionOut(CollectionCreate):
    id: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DocumentOut(BaseModel):
    id: str
    filename: str
    file_hash: str
    file_type: str
    mime_type: str
    size_bytes: int
    status: str
    page_count: int
    chunk_count: int
    error: str | None
    uploaded_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    collection_ids: list[str] = []
    top_k: int = Field(default=6, ge=1, le=30)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class Passage(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    page_number: int | None
    excerpt: str
    score: float
    methods: list[str]


class ChatRequest(SearchRequest):
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    provider: str
    grounded: bool
    insufficient_evidence: bool
    citations: list[Passage]
    conversation_id: str


class EvaluationCase(BaseModel):
    question: str
    expected_document_ids: list[str]


class EvaluationRequest(BaseModel):
    cases: list[EvaluationCase] = Field(min_length=1, max_length=100)
    top_k: int = Field(default=5, ge=1, le=30)

