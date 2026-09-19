FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DANASAFE_ROOT=/app

WORKDIR /app

# The build context is the repository root (configured in wrangler.jsonc).
# Engine/ is the single canonical source used by local development and Cloudflare.
COPY Engine/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY Engine /app/Engine
COPY CloudflareV82/container/server.py /app/server.py

EXPOSE 8080
CMD ["python", "/app/server.py"]
