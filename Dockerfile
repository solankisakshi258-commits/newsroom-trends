# Newsroom Trends — live scheduler + dashboard in one container.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install deps first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code + config.
COPY newsroom_trends ./newsroom_trends
COPY config.yaml .

# Reports + db live here; mount a volume to persist across restarts.
RUN mkdir -p data/reports
VOLUME ["/app/data"]

EXPOSE 8787

# Dashboard healthcheck.
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8787/healthz', timeout=4).read()==b'ok' else 1)"

# Run scheduler + dashboard together; bind dashboard to all interfaces inside the container.
CMD ["python", "-m", "newsroom_trends.cli", "-v", "live", "--host", "0.0.0.0", "--port", "8787"]
