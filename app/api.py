import time
import re
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models import Chunk, Collection, Document, DocumentStatus
from app.providers import generation_provider
from app.schemas import *
from app.services import IngestionError, IngestionService, RetrievalService, chroma_index, embedding_provider, save_conversation


router = APIRouter()


def dependencies(db: Session, settings: Settings):
    embeddings, warning = embedding_provider(settings)
    return embeddings, warning


def passage(item) -> Passage:
    excerpt = item.chunk.text[:600]
    return Passage(chunk_id=item.chunk.id, document_id=item.chunk.document_id,
                   document_name=item.document_name, page_number=item.chunk.page_number,
                   excerpt=excerpt, score=round(item.score, 4), methods=item.methods)


@router.get("/health")
def health(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    db.execute(select(func.count()).select_from(Document)).scalar()
    embeddings, warning = dependencies(db, settings)
    _, chroma_warning = chroma_index(settings, embeddings)
    return {"status": "ok", "database": "connected", "generation_provider": settings.generation_provider,
            "embedding_provider": settings.embedding_provider, "degraded_mode": warning, "vector_store_warning": chroma_warning}


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    return {
        "documents": db.scalar(select(func.count()).select_from(Document)),
        "indexed": db.scalar(select(func.count()).select_from(Document).where(Document.status == DocumentStatus.indexed)),
        "processing": db.scalar(select(func.count()).select_from(Document).where(Document.status == DocumentStatus.processing)),
        "collections": db.scalar(select(func.count()).select_from(Collection)),
    }


@router.post("/collections", response_model=CollectionOut, status_code=201)
def create_collection(body: CollectionCreate, db: Session = Depends(get_db)):
    if db.scalar(select(Collection).where(func.lower(Collection.name) == body.name.strip().lower())):
        raise HTTPException(409, "Collection name already exists")
    value = Collection(name=body.name.strip(), description=body.description.strip())
    db.add(value); db.commit(); return value


@router.get("/collections", response_model=list[CollectionOut])
def list_collections(db: Session = Depends(get_db)):
    return list(db.scalars(select(Collection).order_by(Collection.created_at.desc())))


@router.put("/collections/{collection_id}", response_model=CollectionOut)
def update_collection(collection_id: str, body: CollectionUpdate, db: Session = Depends(get_db)):
    value = db.get(Collection, collection_id)
    if not value: raise HTTPException(404, "Collection not found")
    value.name, value.description = body.name.strip(), body.description.strip(); db.commit(); return value


@router.delete("/collections/{collection_id}", status_code=204)
def delete_collection(collection_id: str, db: Session = Depends(get_db)):
    value = db.get(Collection, collection_id)
    if not value: raise HTTPException(404, "Collection not found")
    db.delete(value); db.commit()


@router.post("/documents", response_model=DocumentOut, status_code=201)
async def upload_document(file: UploadFile = File(...), collection_ids: str = Form(""),
                          db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    embeddings, _ = dependencies(db, settings)
    index, _ = chroma_index(settings, embeddings)
    try:
        return IngestionService(db, settings, embeddings, index).ingest(
            file.filename or "", file.content_type or "", content,
            [x for x in collection_ids.split(",") if x])
    except IngestionError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/documents", response_model=list[DocumentOut])
def documents(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
              status: DocumentStatus | None = None, db: Session = Depends(get_db)):
    statement = select(Document).order_by(Document.uploaded_at.desc()).offset(offset).limit(limit)
    if status: statement = statement.where(Document.status == status)
    return list(db.scalars(statement))


@router.get("/documents/{document_id}", response_model=DocumentOut)
def document(document_id: str, db: Session = Depends(get_db)):
    value = db.get(Document, document_id)
    if not value: raise HTTPException(404, "Document not found")
    return value


@router.get("/documents/{document_id}/chunks")
def document_chunks(document_id: str, db: Session = Depends(get_db)):
    if not db.get(Document, document_id): raise HTTPException(404, "Document not found")
    return [{"id": c.id, "page_number": c.page_number, "chunk_index": c.chunk_index,
             "text": c.text, "char_start": c.char_start, "char_end": c.char_end}
            for c in db.scalars(select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index))]


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    value = db.get(Document, document_id)
    if not value: raise HTTPException(404, "Document not found")
    embeddings, _ = dependencies(db, settings)
    index, _ = chroma_index(settings, embeddings)
    IngestionService(db, settings, embeddings, index).delete(value)


@router.post("/documents/{document_id}/collections/{collection_id}", status_code=204)
def add_to_collection(document_id: str, collection_id: str, db: Session = Depends(get_db)):
    document, collection = db.get(Document, document_id), db.get(Collection, collection_id)
    if not document or not collection: raise HTTPException(404, "Document or collection not found")
    if collection not in document.collections: document.collections.append(collection)
    db.commit()


@router.delete("/documents/{document_id}/collections/{collection_id}", status_code=204)
def remove_from_collection(document_id: str, collection_id: str, db: Session = Depends(get_db)):
    document, collection = db.get(Document, document_id), db.get(Collection, collection_id)
    if not document or not collection: raise HTTPException(404, "Document or collection not found")
    if collection in document.collections: document.collections.remove(collection)
    db.commit()


@router.post("/search", response_model=list[Passage])
@router.post("/retrieval", response_model=list[Passage])
def search(body: SearchRequest, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    embeddings, _ = dependencies(db, settings)
    results = RetrievalService(db, embeddings).search(body.query, body.collection_ids, body.top_k)
    return [passage(x) for x in results if x.score >= body.min_score]


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    embeddings, _ = dependencies(db, settings)
    results = RetrievalService(db, embeddings).search(body.query, body.collection_ids, body.top_k)
    filtered = [x for x in results if x.score >= body.min_score]
    try:
        generator = generation_provider(settings)
        answer, grounded = generator.generate(body.query, filtered)
    except Exception as exc:
        raise HTTPException(502, f"Generation provider failed: {type(exc).__name__}") from exc
    citations = [passage(x) for x in filtered[:6]] if grounded else []
    citation_dicts = [x.model_dump() for x in citations]
    conversation_id = save_conversation(db, body.query, answer, citation_dicts, body.conversation_id)
    return ChatResponse(answer=answer, provider=generator.name, grounded=grounded,
                        insufficient_evidence=not grounded, citations=citations, conversation_id=conversation_id)


@router.post("/summaries/{document_id}")
def summarize(document_id: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    document = db.get(Document, document_id)
    if not document: raise HTTPException(404, "Document not found")
    chunks = list(db.scalars(select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index).limit(8)))
    summary = " ".join(re.split(r"(?<=[.!?])\s+", c.text)[0] for c in chunks if c.text)
    return {"document_id": document_id, "provider": "extractive", "summary": summary[:4000]}


@router.post("/comparison")
def compare(document_a: str, document_b: str, db: Session = Depends(get_db)):
    docs = [db.get(Document, document_a), db.get(Document, document_b)]
    if not all(docs): raise HTTPException(404, "Document not found")
    texts = [" ".join(db.scalars(select(Chunk.text).where(Chunk.document_id == item.id))) for item in docs]
    words = [set(re.findall(r"[a-z0-9]+", value.lower())) for value in texts]
    return {"documents": [document_a, document_b], "shared_terms": sorted(words[0] & words[1])[:100],
            "only_in_first": sorted(words[0] - words[1])[:100], "only_in_second": sorted(words[1] - words[0])[:100]}


@router.post("/evaluation")
def evaluate(body: EvaluationRequest, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    embeddings, _ = dependencies(db, settings); retrieval = RetrievalService(db, embeddings)
    reciprocal, recalled, precision, latency = [], [], [], []
    for case in body.cases:
        started = time.perf_counter(); results = retrieval.search(case.question, [], body.top_k); latency.append((time.perf_counter()-started)*1000)
        found = [x.chunk.document_id for x in results]; expected = set(case.expected_document_ids)
        hits = [i for i, doc in enumerate(found, 1) if doc in expected]
        reciprocal.append(1/min(hits) if hits else 0); recalled.append(len(expected & set(found))/len(expected) if expected else 0)
        precision.append(sum(1 for doc in found if doc in expected)/len(found) if found else 0)
    count = len(body.cases)
    return {"cases": count, "top_k": body.top_k, "recall_at_k": sum(recalled)/count,
            "precision_at_k": sum(precision)/count, "mrr": sum(reciprocal)/count,
            "mean_retrieval_latency_ms": sum(latency)/count, "measured": True}

