# Build:  docker build -t deal-sourcing-agent .
# Run:    docker run -p 8000:8000 \
#           -e DATABASE_URL="postgresql://user:pass@host:25060/deal_sourcing?sslmode=require" \
#           deal-sourcing-agent
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
