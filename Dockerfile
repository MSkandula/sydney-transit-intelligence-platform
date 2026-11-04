# One image for both Azure jobs (ingest and transform). No secrets are baked in: credentials
# arrive at run time from Key Vault through a managed identity.
FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/MSkandula/sydney-transit-intelligence-platform" \
      org.opencontainers.image.description="Sydney transit pipeline: ingest and transform jobs"

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LANDING_DIR=/tmp/landing \
    EXTRACT_DIR=/tmp/extracts \
    DBT_PROFILES_DIR=/app/.dbt

RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY requirements.txt requirements-azure.txt ./
COPY dbt_transit/requirements.txt dbt_transit/requirements.txt
RUN pip install -r requirements-azure.txt

COPY ingestion ingestion
COPY dbt_transit dbt_transit

# dbt packages are fetched at build time; the placeholder values only satisfy profile rendering.
RUN mkdir -p /app/.dbt && cp dbt_transit/profiles.yml.example /app/.dbt/profiles.yml \
 && cd dbt_transit \
 && DATABRICKS_HOST=placeholder DATABRICKS_HTTP_PATH=placeholder DATABRICKS_TOKEN=placeholder dbt deps \
 && chown -R app:app /app

USER app
ENTRYPOINT ["python", "ingestion/jobs.py"]
CMD ["ingest"]
