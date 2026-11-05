FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir .
ENV REVERSA_DATA_DIR=/data PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "reversa_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
