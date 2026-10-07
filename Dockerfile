# API image: FastAPI + LangGraph + Chroma (embedded, persisted on the ./data volume) + Tesseract OCR
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models TRANSFORMERS_OFFLINE=0 ANONYMIZED_TELEMETRY=False
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r requirements.txt

# bake both embedding models into the image -> offline, fast startup
RUN python -c "from sentence_transformers import SentenceTransformer as S; \
S('BAAI/bge-small-en-v1.5'); S('sentence-transformers/all-MiniLM-L6-v2')"
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

COPY . .
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s CMD curl -fs http://localhost:8000/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
