# Architecture

The API layer validates HTTP contracts and delegates to ingestion, retrieval and provider services. SQLAlchemy stores document metadata, chunks, model-tagged vectors, collections and conversations. SQLite is the zero-configuration default; any SQLAlchemy PostgreSQL URL is supported.

Ingestion is `validate → hash → extract → normalize → chunk → embed → persist`. A failed operation rolls back database changes and removes its uploaded file. Cascading foreign keys remove chunks and vectors when a document is deleted.

Retrieval calculates dense cosine ranks and lexical term-overlap ranks, then uses Reciprocal Rank Fusion (`1 / (60 + rank)`). The service is independent from generation and can be inspected through `/retrieval`.

Provider prompts delimit evidence and state that document text is untrusted data. The extractive provider is the safe default. External providers receive only the question and retrieved passages, not the entire library.

Trade-offs: the local vector table is simple and deterministic but linear-scan; Chroma/Sentence Transformers are optional because their model and runtime footprint is significant on an 8 GB machine.

