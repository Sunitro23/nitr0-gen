# Utiliser une image Python officielle (ici Python 3.9 slim, vous pouvez adapter)
FROM python:3.11.11-slim

# Définir le répertoire de travail
WORKDIR /app

# Copier les fichiers de dépendances (si vous avez un requirements.txt)
COPY requirements.txt .

# Installer les dépendances
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copier tout le reste de votre projet dans le conteneur
COPY . .

CMD ["python", "main.py"]
