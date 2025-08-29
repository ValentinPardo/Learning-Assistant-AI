FROM python:3.9
WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements.txt desde el directorio padre
COPY ../requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo el proyecto desde el directorio padre
COPY .. .

# Ejecutar uvicorn apuntando al main.py en learning_platform
CMD ["uvicorn", "learning_platform.main:app", "--host", "0.0.0.0", "--port", "8000"]