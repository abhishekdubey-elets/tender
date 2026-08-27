# GovIntel backend on a Hugging Face Docker Space.
# Build context = the Space repo root, which must contain (copied from backend/):
#   app/  alembic/  alembic.ini   alongside this Dockerfile and README.md
# HF Spaces serve on port 7860. Secrets (MONGODB_URI, API_KEYS) are injected as env.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    USE_MONGO=true \
    MONGODB_DB=govintel

WORKDIR /app

# Runtime deps (mirrors backend/pyproject.toml [project.dependencies]). Postgres
# drivers are installed for import-safety but the Mongo serving path never connects.
RUN pip install \
    "sqlalchemy>=2.0.30" "alembic>=1.13" "psycopg[binary]>=3.1" "pgvector>=0.3.0" \
    "pydantic>=2.7" "pydantic-settings>=2.2" "python-dotenv>=1.0" "anthropic>=0.40" \
    "fastapi>=0.110" "uvicorn[standard]>=0.29" "websockets>=12" "pymongo[srv]>=4.6" \
    "httpx>=0.27" "beautifulsoup4>=4.12" "lxml>=5.0" "feedparser>=6.0" \
    "openpyxl>=3.1" "pypdf>=4.0" "python-docx>=1.1"

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 7860
# Shell form so $PORT (Render/Fly/Koyeb) is honoured; defaults to 7860 (HF Spaces).
CMD uvicorn app.api:create_app --factory --host 0.0.0.0 --port ${PORT:-7860}
