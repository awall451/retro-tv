# Retro TV channel tracker: Python standard library only, no pip installs.
# See README.md in this folder.
FROM python:3.13.9-alpine3.22

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION} \
    DATA_DIR=/data \
    PORT=8080 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# tzdata: watch minutes are counted per local day and hour (TRACKER_TZ).
RUN apk add --no-cache tzdata

# Fixed uid/gid, so a host folder mounted at /data can be chowned to match.
RUN addgroup -S -g 10001 tracker && adduser -S -D -H -u 10001 -G tracker tracker \
    && mkdir -p /data && chown tracker:tracker /data

WORKDIR /app
COPY app/server.py /app/server.py
COPY app/static /app/static
# The history renumbering tool (README.md, "Renumbering channels"); run by hand.
COPY tools/renumber.py /app/renumber.py

USER 10001:10001
EXPOSE 8080
VOLUME ["/data"]
HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python3", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4).status == 200 else 1)"]
CMD ["python3", "-I", "/app/server.py"]
