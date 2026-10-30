# Imagem enxuta de Python; a porta e o comando correspondem ao servidor FastAPI.
FROM python:3.12-slim
WORKDIR /srv/campaignflow
# Copia dependências primeiro para permitir reutilização do cache de build.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Adiciona o código e prepara a pasta persistente para arquivos importados.
COPY . .
RUN mkdir -p data/raw
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
