FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --create-home app
COPY pyproject.toml ./
COPY app app
RUN pip install --no-cache-dir .
RUN mkdir -p /app/data /app/uploads /app/chroma_data && chown -R app:app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/v1/health')"
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]

