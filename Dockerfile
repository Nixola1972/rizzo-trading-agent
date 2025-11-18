# ===========================================
# DOCKERFILE - Rizzo Trading Agent
# ===========================================
# Immagine Python ottimizzata per il trading bot

FROM python:3.11-slim

# Metadata
LABEL maintainer="Rizzo AI Academy"
LABEL description="AI-powered cryptocurrency trading bot"
LABEL version="1.0"

# Evita prompt interattivi durante installazione
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Installa dipendenze di sistema necessarie per le librerie Python
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    build-essential \
    libpq-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Crea directory di lavoro
WORKDIR /app

# Copia requirements e installa dipendenze Python
# (copiamo prima requirements per sfruttare la cache Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia il codice dell'applicazione
COPY . .

# Crea directory per i log (opzionale, se vuoi loggare in file)
RUN mkdir -p /app/logs

# Permessi (esegui come utente non-root per sicurezza)
RUN useradd -m -u 1000 tradingbot && \
    chown -R tradingbot:tradingbot /app

USER tradingbot

# Comando di default (esegue il bot)
CMD ["python3", "main.py"]
