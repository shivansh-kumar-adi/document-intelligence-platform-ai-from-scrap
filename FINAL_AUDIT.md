# Final audit

Date: 2026-11-01. Environment: Windows 11, Python 3.11.9, Node 22.23.2, npm 11.7.0. Docker CLI was present; its Linux engine was unavailable.

## Executed verification

- `python -m compileall -q app`: passed.
- `pytest`: 12 passed, 0 failed. Six deprecation warnings originate from PyMuPDF native bindings and Starlette's test adapter.
- Full API test: multipart TXT ingestion → embedding/indexing → chat → citation validation → deletion → retrieval cleanup passed.
- `pip check`: no broken requirements.
- `npm install`: generated `package-lock.json`.
- `npm run typecheck`: passed with strict TypeScript.
- `npm run build`: passed; 41 modules, JS 218.26 kB (69.85 kB gzip), CSS 4.86 kB (1.70 kB gzip).
- `npm audit --omit=dev`: zero known production vulnerabilities at execution time.
- `docker compose config --quiet`: passed.
- FastAPI route inventory: all documented `/api/v1` groups were present.

## Tested behavior

Empty/invalid uploads, filename and type validation, chunk boundaries, page metadata, embedding dimensions, SHA-256 duplicates, persistent SQL vectors, hybrid rank fusion, citation records, unrelated-query refusal, prompt trust boundary, API validation, provider health disclosure, complete local RAG path, deletion and vector cleanup.

## Not verified

- Docker image build/runtime because Docker Engine was unavailable.
- The optional ChromaDB adapter and Sentence Transformer model because heavyweight AI extras and model weights were intentionally not installed.
- Gemini and Ollama calls because no provider was configured.
- PostgreSQL runtime; the SQLAlchemy URL is supported but tests used SQLite.
- PDF/DOCX fixtures beyond extraction library imports; automated tests exercised text ingestion and invalid PDF signatures.
- Large-corpus performance and accuracy; no benchmark values are claimed.

## Known constraints

The built-in persistent vector search is a linear scan designed for a portfolio/local workload. Production scale would require Chroma or another vector service, queued ingestion, tenant authentication, quotas, observability and a formal privacy review. External providers receive the question and retrieved evidence. The extractive provider remains fully local.

