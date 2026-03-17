FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir uv && \
    uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv pip install .

# Pre-download the embedding model so first search is fast
RUN . /app/.venv/bin/activate && \
    python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='sentence-transformers/all-MiniLM-L6-v2')" || true


FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY searxng/settings.yml.template /app/searxng/settings.yml.template

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["open-search-mcp"]
