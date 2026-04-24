FROM python:3.12-slim

WORKDIR /app

# System deps (psycopg + build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
   build-essential libpq-dev curl \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY apps/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy app
COPY apps/api /app

# Copy schemas (needed by LLM service for JSON validation)
COPY schemas /schemas

# Copy scripts
COPY scripts /scripts

# Default command
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
