# Demonstration

1. Copy `.env.example` to `.env`; set `EMBEDDING_PROVIDER=hash` for an offline demo.
2. Start `uvicorn app.main:app --reload` and `npm run dev` in `frontend`.
3. Create a collection, upload a TXT/PDF/DOCX, and observe its real indexed page/chunk counts.
4. Ask a question in AI Workspace and inspect each source excerpt, score, method and chunk ID.
5. Use Retrieval Explorer to inspect hybrid ranking separately from generation.
6. Upload the same file again to demonstrate SHA-256 duplicate rejection.
7. Ask an unsupported question to demonstrate the insufficient-evidence response.
8. Delete the document, repeat retrieval, and confirm it no longer appears.

For an external-provider demo, explicitly configure Ollama or Gemini and explain that retrieved passages leave the local process. Never enter sensitive documents when using an external provider without authorization.

