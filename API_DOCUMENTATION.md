# API documentation

Interactive OpenAPI: `http://localhost:8000/docs`. All routes use `/api/v1`.

| Method | Route | Purpose |
|---|---|---|
| GET | `/health`, `/dashboard` | Runtime/provider state and real counts |
| POST/GET/PUT/DELETE | `/collections[/{id}]` | Collection lifecycle |
| POST/GET/DELETE | `/documents[/{id}]` | Upload, list, inspect and delete |
| GET | `/documents/{id}/chunks` | Extracted passages and offsets |
| POST/DELETE | `/documents/{id}/collections/{collectionId}` | Collection membership |
| POST | `/search`, `/retrieval` | Hybrid passages with scores and methods |
| POST | `/chat` | Grounded answer, provider label and citations |
| POST | `/summaries/{documentId}` | Extractive document summary |
| POST | `/comparison?document_a=&document_b=` | Shared and differing vocabulary |
| POST | `/evaluation` | Measured Recall@K, Precision@K, MRR and latency |

Upload is multipart with `file` and optional comma-separated `collection_ids`. Search bodies contain `query`, `collection_ids`, `top_k`, and `min_score`. Validation errors use FastAPI's structured 422 response; missing resources return 404; duplicates return 422 with the existing document ID.

