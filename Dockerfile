FROM python:3.11-slim

# Disable Python output buffering for real-time logs
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies for psycopg2 and other packages
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Use entrypoint.sh as the container entry point
# This ensures ONLY ONE container runs both main.py and sentinel.py correctly
ENTRYPOINT ["/app/entrypoint.sh"]
