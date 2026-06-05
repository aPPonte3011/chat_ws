# Usar imagen base de Python
FROM python:3.11-slim

# Instalar dependencias del sistema necesarias para WeasyPrint
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    libcairo2 \
    libcairo2-dev \
    && rm -rf /var/lib/apt/lists/*

# Establecer directorio de trabajo
WORKDIR /app

# Copiar requirements e instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Exponer el puerto (Render lo asigna dinámicamente)
EXPOSE 8000

# Comando de inicio con Gunicorn
CMD gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 wsgi:app