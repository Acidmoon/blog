FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8082 \
    WEB_CONCURRENCY=2 \
    GUNICORN_TIMEOUT=120

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY app.py config.py models.py module_loader.py home_layout.json ./
COPY modules ./modules
COPY routes ./routes
COPY services ./services
COPY static ./static
COPY templates ./templates

RUN mkdir -p /app/data/articles /app/static/images

EXPOSE 8082

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.getenv('PORT', '8082'), timeout=3).read(1)" || exit 1

CMD ["sh", "-c", "gunicorn --workers ${WEB_CONCURRENCY:-2} --timeout ${GUNICORN_TIMEOUT:-120} --access-logfile - --error-logfile - --bind 0.0.0.0:${PORT:-8082} app:app"]
