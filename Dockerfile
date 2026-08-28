FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Tehran local time: Debian-slim ships without a tz database, so a plain
# TZ=... env var is silently ignored and daily reports / log rotation roll at
# UTC midnight (4:30am Tehran) instead. Placed after pip install to keep the
# dependency layer cached.
ENV TZ=Asia/Tehran
RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# full app incl. web_admin.py + web/ templates + memory/skills/a2a modules
COPY . .

ENV WEB_PORT=8080 \
    PYTHONUNBUFFERED=1

EXPOSE 8080

# Railway healthcheck — /healthz is unauthenticated and returns {ok, version}.
HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=5).status==200 else 1)"

CMD ["python", "bot.py"]
