# Build from the repository root: docker build -f backend/Dockerfile .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
# The CPU build of PyTorch is enough for tabular inference and is several gigabytes smaller.
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r backend/requirements.txt

COPY backend/app backend/app
COPY backend/alembic backend/alembic
COPY backend/alembic.ini backend/alembic.ini
COPY database database
COPY ml/__init__.py ml/__init__.py
COPY ml/preprocessing ml/preprocessing
COPY ml/evaluation ml/evaluation
COPY ml/models ml/models
COPY ml/scripts ml/scripts
COPY ml/data ml/data
COPY scripts scripts

RUN useradd --create-home --uid 1000 proptwin \
    && mkdir -p storage ml/artifacts blockchain \
    && chown -R proptwin:proptwin storage ml/artifacts
USER proptwin

WORKDIR /app/backend
EXPOSE 8000
ENTRYPOINT ["sh", "/app/scripts/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
