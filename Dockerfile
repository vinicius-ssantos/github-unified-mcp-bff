FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml requirements.lock ./
COPY app/ ./app/

RUN pip install --no-cache-dir . --constraint requirements.lock

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
