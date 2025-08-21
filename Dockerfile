# Fase de construcción
FROM python:3.13.6 AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
    
WORKDIR /app

# Instalar dependencias
RUN python -m venv .venv
COPY requirements.txt ./
RUN .venv/bin/pip install -r requirements.txt

# Fase final
FROM python:3.13.6-slim

WORKDIR /app

# Configurar PYTHONPATH para que incluya el directorio raíz
ENV PYTHONPATH="/app"

# Copiar los archivos __init__.py
COPY api/__init__.py api/
COPY lib/__init__.py lib/

# Copiar el entorno virtual y el código
COPY --from=builder /app/.venv .venv/
COPY . .

# Comando corregido con FLASK_APP explícito
CMD ["/app/.venv/bin/flask", "run", "api.chat_api:app", "--host=0.0.0.0", "--port=8080"]
