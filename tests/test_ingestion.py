from pathlib import Path
import pytest
from sqlalchemy import func, select
from app.models import Chunk, ChunkVector, Document
from app.services import HashEmbeddings, IngestionError, IngestionService, PageText, chunk_pages, validate_upload


def test_rejects_empty_and_mismatched_files(settings):
    with pytest.raises(IngestionError, match="empty"):
        validate_upload("empty.txt", "text/plain", b"", settings)
    with pytest.raises(IngestionError, match="signature"):
        validate_upload("fake.pdf", "application/pdf", b"not a pdf", settings)
    with pytest.raises(IngestionError, match="supported"):
        validate_upload("malware.exe", "application/octet-stream", b"MZ123", settings)


def test_chunking_preserves_page_and_overlap():
    text = "First sentence explains alpha. Second sentence adds beta. " * 8
    chunks = chunk_pages([PageText(3, text)], 140, 25)
    assert len(chunks) > 1
    assert all(item[0] == 3 and len(item[1]) <= 180 for item in chunks)
    assert chunks[0][2] <= chunks[1][2]


def test_ingests_txt_vectors_and_detects_duplicate(db, settings):
    service = IngestionService(db, settings, HashEmbeddings())
    content = b"Alpha policy requires approval.\n\nBeta policy requires review."
    document = service.ingest("policy.txt", "text/plain", content, [])
    assert document.status.value == "indexed"
    assert document.chunk_count >= 1
    assert db.scalar(select(func.count()).select_from(ChunkVector)) == document.chunk_count
    vector = db.scalar(select(ChunkVector))
    assert vector.dimensions == 256
    with pytest.raises(IngestionError, match="Duplicate"):
        service.ingest("copy.txt", "text/plain", content, [])


def test_delete_removes_file_chunks_and_vectors(db, settings):
    service = IngestionService(db, settings, HashEmbeddings())
    document = service.ingest("delete.txt", "text/plain", b"Delete this indexed evidence safely.", [])
    stored = Path(document.stored_path)
    service.delete(document)
    assert not stored.exists()
    assert db.scalar(select(func.count()).select_from(Document)) == 0
    assert db.scalar(select(func.count()).select_from(Chunk)) == 0
    assert db.scalar(select(func.count()).select_from(ChunkVector)) == 0

