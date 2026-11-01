import hashlib
import json
import math
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import fitz
from docx import Document as DocxDocument
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Chunk, ChunkVector, Collection, Conversation, Document, DocumentStatus, Message


ALLOWED = {
    ".pdf": {"application/pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/octet-stream"},
    ".txt": {"text/plain", "application/octet-stream"},
}


class IngestionError(ValueError):
    pass


@dataclass
class PageText:
    page: int | None
    text: str


def safe_filename(name: str) -> str:
    leaf = Path(name).name
    clean = re.sub(r"[^A-Za-z0-9._ -]", "_", leaf).strip(" .")
    if not clean or clean in {".", ".."}:
        raise IngestionError("Invalid filename")
    return clean[:200]


def validate_upload(name: str, mime: str, content: bytes, settings: Settings) -> tuple[str, str]:
    filename = safe_filename(name)
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED:
        raise IngestionError("Only PDF, DOCX, and TXT files are supported")
    if not content or not content.strip(b"\x00\r\n\t "):
        raise IngestionError("Document is empty")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise IngestionError(f"File exceeds {settings.max_upload_mb} MB limit")
    normalized_mime = (mime or mimetypes.guess_type(filename)[0] or "application/octet-stream").split(";")[0]
    if normalized_mime not in ALLOWED[ext]:
        raise IngestionError(f"MIME type {normalized_mime} does not match {ext}")
    if ext == ".pdf" and not content.startswith(b"%PDF"):
        raise IngestionError("File extension is PDF but signature is invalid")
    if ext == ".docx" and not content.startswith(b"PK"):
        raise IngestionError("File extension is DOCX but ZIP signature is invalid")
    return filename, normalized_mime


def extract_pages(path: Path, file_type: str) -> list[PageText]:
    try:
        if file_type == ".pdf":
            with fitz.open(path) as pdf:
                pages = [PageText(i + 1, page.get_text("text")) for i, page in enumerate(pdf)]
        elif file_type == ".docx":
            doc = DocxDocument(path)
            pages = [PageText(None, "\n\n".join(p.text for p in doc.paragraphs))]
        else:
            pages = [PageText(None, path.read_text(encoding="utf-8", errors="strict"))]
    except Exception as exc:
        raise IngestionError(f"Document extraction failed: {type(exc).__name__}") from exc
    pages = [PageText(p.page, re.sub(r"[ \t]+", " ", p.text).strip()) for p in pages]
    if not any(p.text for p in pages):
        raise IngestionError("Document contains no extractable text")
    return pages


def chunk_pages(pages: list[PageText], size: int, overlap: int) -> list[tuple[int | None, str, int, int]]:
    if size < 100 or overlap < 0 or overlap >= size:
        raise ValueError("chunk size must be >=100 and overlap must be smaller than size")
    chunks: list[tuple[int | None, str, int, int]] = []
    global_offset = 0
    for page in pages:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", page.text) if p.strip()]
        if not paragraphs:
            paragraphs = [page.text]
        buffer = ""
        start = 0
        for paragraph in paragraphs:
            sentences = re.split(r"(?<=[.!?])\s+", paragraph)
            for sentence in sentences:
                if buffer and len(buffer) + len(sentence) + 1 > size:
                    chunks.append((page.page, buffer.strip(), global_offset + start, global_offset + start + len(buffer.strip())))
                    tail = buffer[-overlap:] if overlap else ""
                    cut = tail.find(" ")
                    buffer = tail[cut + 1:] if cut >= 0 else tail
                    start = max(0, start + len(buffer) - overlap)
                buffer = f"{buffer} {sentence}".strip()
            buffer += "\n\n"
        if buffer.strip():
            chunks.append((page.page, buffer.strip(), global_offset + start, global_offset + start + len(buffer.strip())))
        global_offset += len(page.text) + 1
    return chunks


class Embeddings(Protocol):
    model_name: str
    dimensions: int
    def encode(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbeddings:
    """Deterministic offline fallback; intended for tests and degraded local operation."""
    model_name = "deterministic-hash-v1"
    dimensions = 256

    def encode(self, texts: list[str]) -> list[list[float]]:
        result = []
        for value in texts:
            vector = [0.0] * self.dimensions
            for token in re.findall(r"[a-z0-9]+", value.lower()):
                digest = hashlib.sha256(token.encode()).digest()
                vector[int.from_bytes(digest[:2], "big") % self.dimensions] += 1.0
            norm = math.sqrt(sum(x * x for x in vector)) or 1.0
            result.append([x / norm for x in vector])
        return result


class SentenceTransformerEmbeddings:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer
        self.model_name = model_name
        self._model = SentenceTransformer(model_name)
        self.dimensions = self._model.get_sentence_embedding_dimension()

    def encode(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True).tolist()


class ChromaIndex:
    """Optional persistent ANN mirror. SQL remains the metadata source of truth."""
    def __init__(self, path: Path, model_name: str, dimensions: int):
        import chromadb
        safe_model = re.sub(r"[^a-zA-Z0-9_-]", "_", model_name)[:40]
        self.collection = chromadb.PersistentClient(path=str(path)).get_or_create_collection(
            name=f"chunks_{safe_model}_{dimensions}", metadata={"model": model_name, "dimensions": dimensions})

    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        self.collection.upsert(ids=[c.id for c in chunks], embeddings=vectors,
                               documents=[c.text for c in chunks],
                               metadatas=[{"document_id": c.document_id, "page": c.page_number or 0} for c in chunks])

    def delete_document(self, document_id: str) -> None:
        self.collection.delete(where={"document_id": document_id})


def chroma_index(settings: Settings, embeddings: Embeddings) -> tuple[ChromaIndex | None, str | None]:
    try:
        return ChromaIndex(settings.chroma_dir, embeddings.model_name, embeddings.dimensions), None
    except ImportError:
        return None, "ChromaDB is not installed; SQL vector persistence remains active"


def embedding_provider(settings: Settings) -> tuple[Embeddings, str | None]:
    if settings.embedding_provider == "hash":
        return HashEmbeddings(), None
    try:
        return SentenceTransformerEmbeddings(settings.embedding_model), None
    except Exception as exc:
        return HashEmbeddings(), f"Sentence Transformers unavailable: {type(exc).__name__}; using declared hash fallback"


def cosine(a: list[float], b: list[float]) -> float:
    return max(0.0, sum(x * y for x, y in zip(a, b)))


class IngestionService:
    def __init__(self, db: Session, settings: Settings, embeddings: Embeddings, index: ChromaIndex | None = None):
        self.db, self.settings, self.embeddings, self.index = db, settings, embeddings, index

    def ingest(self, filename: str, mime: str, content: bytes, collection_ids: list[str]) -> Document:
        filename, mime = validate_upload(filename, mime, content, self.settings)
        digest = hashlib.sha256(content).hexdigest()
        duplicate = self.db.scalar(select(Document).where(Document.file_hash == digest))
        if duplicate:
            raise IngestionError(f"Duplicate document: {duplicate.id}")
        path = self.settings.upload_dir / f"{digest}{Path(filename).suffix.lower()}"
        path.write_bytes(content)
        document = Document(filename=filename, stored_path=str(path), file_hash=digest,
                            file_type=Path(filename).suffix.lower(), mime_type=mime, size_bytes=len(content),
                            status=DocumentStatus.processing)
        document.collections = list(self.db.scalars(select(Collection).where(Collection.id.in_(collection_ids)))) if collection_ids else []
        self.db.add(document)
        self.db.flush()
        try:
            pages = extract_pages(path, document.file_type)
            parts = chunk_pages(pages, self.settings.chunk_size, self.settings.chunk_overlap)
            chunks = [Chunk(document_id=document.id, chunk_index=i, page_number=p, text=value,
                            char_start=start, char_end=end) for i, (p, value, start, end) in enumerate(parts)]
            self.db.add_all(chunks)
            self.db.flush()
            vectors = self.embeddings.encode([chunk.text for chunk in chunks])
            if any(len(v) != self.embeddings.dimensions for v in vectors):
                raise IngestionError("Embedding dimension mismatch")
            self.db.add_all([ChunkVector(chunk_id=c.id, model_name=self.embeddings.model_name,
                                         dimensions=self.embeddings.dimensions, vector_json=json.dumps(v))
                             for c, v in zip(chunks, vectors)])
            if self.index:
                self.index.upsert(chunks, vectors)
            document.page_count = len(pages)
            document.chunk_count = len(chunks)
            document.status = DocumentStatus.indexed
            self.db.commit()
            return document
        except Exception as exc:
            self.db.rollback()
            failed = self.db.get(Document, document.id)
            if failed:
                failed.status = DocumentStatus.failed
                failed.error = str(exc)[:1000]
                self.db.commit()
            path.unlink(missing_ok=True)
            raise

    def delete(self, document: Document) -> None:
        if self.index:
            self.index.delete_document(document.id)
        Path(document.stored_path).unlink(missing_ok=True)
        chunk_ids = select(Chunk.id).where(Chunk.document_id == document.id)
        self.db.execute(delete(ChunkVector).where(ChunkVector.chunk_id.in_(chunk_ids)))
        self.db.delete(document)
        self.db.commit()


@dataclass
class RankedChunk:
    chunk: Chunk
    document_name: str
    score: float
    methods: list[str]


class RetrievalService:
    def __init__(self, db: Session, embeddings: Embeddings):
        self.db, self.embeddings = db, embeddings

    def search(self, query: str, collection_ids: list[str], top_k: int) -> list[RankedChunk]:
        statement = select(Chunk, Document.filename, ChunkVector).join(Document).join(ChunkVector)
        if collection_ids:
            statement = statement.join(Document.collections).where(Collection.id.in_(collection_ids))
        rows = list(self.db.execute(statement).all())
        query_vector = self.embeddings.encode([query])[0]
        terms = set(re.findall(r"[a-z0-9]+", query.lower()))
        dense_scores = {r[0].id: cosine(query_vector, json.loads(r[2].vector_json)) for r in rows}
        keyword_scores = {r[0].id: len(terms & set(re.findall(r"[a-z0-9]+", r[0].text.lower()))) / max(1, len(terms)) for r in rows}
        dense = sorted(rows, key=lambda r: dense_scores[r[0].id], reverse=True)
        keyword = sorted(rows, key=lambda r: keyword_scores[r[0].id], reverse=True)
        fused: dict[str, tuple[float, set[str], tuple]] = {}
        for method, ranking in (("dense", dense), ("keyword", keyword)):
            for rank, row in enumerate(ranking[: max(top_k * 4, 20)], 1):
                score, methods, _ = fused.get(row[0].id, (0.0, set(), row))
                methods.add(method)
                fused[row[0].id] = (score + 1 / (60 + rank), methods, row)
        ordered = sorted(fused.values(), key=lambda item: item[0], reverse=True)[:top_k]
        maximum = max((x[0] for x in ordered), default=1.0)
        return [RankedChunk(row[0], row[1], (score / maximum) *
                            (0.65 * dense_scores[row[0].id] + 0.35 * keyword_scores[row[0].id]), sorted(methods))
                for score, methods, row in ordered]


class ExtractiveGenerator:
    name = "extractive"
    def generate(self, question: str, passages: list[RankedChunk]) -> tuple[str, bool]:
        if not passages or passages[0].score < 0.15:
            return "I do not have sufficient evidence in the selected documents to answer that question.", False
        sentences = []
        terms = set(re.findall(r"[a-z0-9]+", question.lower()))
        for passage in passages[:4]:
            candidates = re.split(r"(?<=[.!?])\s+", passage.chunk.text)
            best = max(candidates, key=lambda s: len(terms & set(re.findall(r"[a-z0-9]+", s.lower()))), default="")
            if best and best not in sentences:
                sentences.append(best.strip())
        return " ".join(sentences[:4]), bool(sentences)


def save_conversation(db: Session, question: str, answer: str, citations: list[dict], conversation_id: str | None) -> str:
    conversation = db.get(Conversation, conversation_id) if conversation_id else None
    if not conversation:
        conversation = Conversation(title=question[:200])
        db.add(conversation)
        db.flush()
    db.add_all([Message(conversation_id=conversation.id, role="user", content=question),
                Message(conversation_id=conversation.id, role="assistant", content=answer,
                        citations_json=json.dumps(citations))])
    db.commit()
    return conversation.id

