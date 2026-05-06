# Stage 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /app

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir ".[llm,auth,knowledge]"

COPY src/ ./src/

# Stage 2: Runtime
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

RUN useradd --create-home fastapp

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app/src ./src
COPY --from=builder /app/pyproject.toml ./

USER fastapp

EXPOSE 8000

CMD ["fast-app", "serve"]