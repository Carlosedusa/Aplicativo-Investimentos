FROM python:3.12-slim
WORKDIR /srv
COPY server/pyproject.toml server/pyproject.toml
RUN pip install --no-cache-dir "fastapi>=0.110" "uvicorn>=0.29" "httpx>=0.27"
COPY engine engine
COPY server server
COPY web web
WORKDIR /srv/server
ENV WORKDIR=/data
VOLUME /data
EXPOSE 8000
# Defina API_TOKEN (obrigatório) e, se quiser, SEC_USER_AGENT e STARTING_CASH.
CMD ["python", "-m", "uvicorn", "app.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
