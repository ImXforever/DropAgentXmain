FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Tehran local time (daily reports / log rotation at local midnight, not UTC).
ENV TZ=Asia/Tehran
RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

COPY . .

ENV WEB_PORT=8081 \
    PYTHONUNBUFFERED=1

EXPOSE 8081

HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8081/healthz', timeout=5).status==200 else 1)"

CMD ["python", "bot.py"]
