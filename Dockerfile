FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo \
    gosu \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ARG APP_UID=1000
ARG APP_GID=1000

# CRLF düzelt; yazılabilir dizinler; non-root kullanıcı (entrypoint root'tan gosu ile düşer)
RUN sed -i 's/\r$//' /app/docker-entrypoint.sh \
    && chmod +x /app/docker-entrypoint.sh \
    && mkdir -p static/item_pics static/profile_pics logs \
    && groupadd --gid ${APP_GID} atikport \
    && useradd --uid ${APP_UID} --gid atikport --home-dir /app --shell /usr/sbin/nologin atikport \
    && chown -R atikport:atikport /app

ENV FLASK_APP=app.py
ENV AUTO_CREATE_DB=False
EXPOSE 5000

# Entrypoint root olarak volume izinlerini düzeltir; uygulama gosu ile atikport kullanıcısında çalışır
ENTRYPOINT ["/bin/sh", "/app/docker-entrypoint.sh"]
