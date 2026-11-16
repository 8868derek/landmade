FROM python:3.12-slim-bookworm

WORKDIR /app

COPY requirements.txt requirements-images.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DEPLOYMENT=public \
    DATA_DIR=/data \
    PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["python3", "server.py"]
