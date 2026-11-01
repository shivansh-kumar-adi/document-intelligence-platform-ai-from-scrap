from app.services import ExtractiveGenerator, HashEmbeddings, IngestionService, RetrievalService


def indexed(db, settings):
    service = IngestionService(db, settings, HashEmbeddings())
    first = service.ingest("security.txt", "text/plain", b"Access tokens expire after fifteen minutes. Refresh tokens rotate after use.", [])
    second = service.ingest("inventory.txt", "text/plain", b"Inventory reservation uses an atomic conditional database update to prevent overselling.", [])
    return first, second


def test_hybrid_retrieval_ranks_matching_document(db, settings):
    first, _ = indexed(db, settings)
    results = RetrievalService(db, HashEmbeddings()).search("How do refresh tokens rotate?", [], 3)
    assert results[0].chunk.document_id == first.id
    assert set(results[0].methods) == {"dense", "keyword"}
    assert 0 <= results[0].score <= 1


def test_extractive_answer_is_grounded_and_citable(db, settings):
    indexed(db, settings)
    results = RetrievalService(db, HashEmbeddings()).search("How is overselling prevented?", [], 2)
    answer, grounded = ExtractiveGenerator().generate("How is overselling prevented?", results)
    assert grounded
    assert "atomic" in answer.lower()
    assert results[0].chunk.id and results[0].document_name


def test_insufficient_evidence_is_explicit():
    answer, grounded = ExtractiveGenerator().generate("Unknown?", [])
    assert not grounded
    assert "sufficient evidence" in answer


def test_unrelated_query_is_insufficient_even_when_library_has_documents(db, settings):
    indexed(db, settings)
    results = RetrievalService(db, HashEmbeddings()).search("quantum zebras mars", [], 2)
    answer, grounded = ExtractiveGenerator().generate("quantum zebras mars", results)
    assert not grounded
    assert "sufficient evidence" in answer

