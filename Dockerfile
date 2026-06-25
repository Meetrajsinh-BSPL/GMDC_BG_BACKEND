FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    libfontconfig1 \
    curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --shell /bin/bash appuser \
 && mkdir -p /app/certs /tmp/uploads /home/appuser/.oci \
 && chown -R appuser:appuser /app /tmp/uploads /home/appuser/.oci

COPY --chown=appuser:appuser *.py /app/
COPY --chown=appuser:appuser entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER appuser

EXPOSE 5000

ENV PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    OCI_CONFIG_FILE=/home/appuser/.oci/config

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:5000/health || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "--timeout", "180", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
