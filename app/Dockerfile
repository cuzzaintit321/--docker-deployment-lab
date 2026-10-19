FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home appuser
COPY server.py .
USER appuser
EXPOSE 8000
CMD ["python", "server.py"]
