FROM python:3.12-slim

WORKDIR /app

# Install system deps needed by some Python packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY . .

# The agents.config.json lives at project root — mounted via docker-compose
# Backend reads it from ../agents.config.json relative to backend/
# We'll handle this with a volume mount in docker-compose

EXPOSE 8000

CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000"]
