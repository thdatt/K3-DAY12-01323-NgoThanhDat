# ============================================================
# Dockerfile — Stateless Agent with Redis Session (Scaling Demo)
# ============================================================

FROM python:3.11-slim AS builder

WORKDIR /app

# ✅ FIX: đã bỏ `apt-get install gcc libpq-dev`.
# Dependencies của project (fastapi, uvicorn[standard], redis) đều có sẵn
# wheel dựng sẵn cho manylinux/CPython 3.11 — pip tải về dùng luôn, không
# cần biên dịch gì cả. Cài gcc ở đây tốn thêm ~200 MB tải về và nhiều phút
# build mà không dùng tới một lần nào.
# Chỉ thêm lại apt-get khi requirements có package thật sự phải compile
# (ví dụ psycopg2 bản source, hoặc numpy trên kiến trúc lạ).

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


FROM python:3.11-slim AS runtime

RUN groupadd -r agent && useradd -r -g agent -d /app agent

WORKDIR /app

COPY --from=builder /root/.local /home/agent/.local

COPY app.py .
COPY utils/ ./utils/

RUN chown -R agent:agent /app

USER agent

ENV PATH=/home/agent/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Ensure user-installed packages are found
ENV PYTHONUSERBASE=/home/agent/.local

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c \
    "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
    || exit 1

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
