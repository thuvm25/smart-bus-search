FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY benchmark/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY benchmark/benchmark.py .

CMD ["python", "benchmark.py"]
