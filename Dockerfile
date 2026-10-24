# CPU runtime for both Apple Silicon and x86 PCs. Ollama is a separate service.
FROM python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/cache/huggingface \
    FINBERT_REVISION=0bc2ac10dda6929bcb1f77ccc43c7ec5c424f031

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential ca-certificates libgomp1 libglib2.0-0 libgl1 tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
COPY docker/constraints.txt /tmp/constraints.txt
# Avoid installing the multi-GB CUDA dependencies on CPU-only Docker Desktop.
RUN python -m pip install --no-cache-dir 'torch==2.14.1' --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install --no-cache-dir -r /tmp/requirements.txt -c /tmp/constraints.txt \
    && python -m spacy download en_core_web_sm \
    && python -m pip check

COPY . /app
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
