FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --requirement requirements.txt

COPY app ./app
COPY docs/contracts ./docs/contracts
COPY migrations ./migrations
COPY scripts ./scripts
COPY server.py ./

RUN python -m compileall -q app scripts server.py
RUN useradd --create-home --uid 10001 orion
USER orion

EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
