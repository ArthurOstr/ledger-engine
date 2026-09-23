FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl  \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --gid 1000 appgroup && \
    adduser --uid 1000 --gid 1000 --disabled-password --gecos "" appuser
RUN mkdir -p /tmp/statement_uploads &&  \
    chown -R appuser:appgroup /tmp/statement_uploads
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=appuser:appgroup . .
USER appuser
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]