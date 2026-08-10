# ============================================================
# Production Dockerfile — Multi-stage, < 500 MB, non-root
# ============================================================

# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /build

# ✅ FIX: đã bỏ `apt-get install gcc libpq-dev`.
# Toàn bộ dependencies (fastapi, uvicorn[standard], pydantic, pyjwt,
# python-dotenv, redis, psutil) đều có wheel dựng sẵn cho manylinux/CPython
# 3.11 — pip tải về dùng ngay, không biên dịch gì. Cài gcc chỉ tốn thêm
# ~200 MB tải và vài phút build mà không dùng tới.
# Chỉ thêm lại khi requirements có package buộc phải compile từ source.

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# Stage 2: Runtime
FROM python:3.11-slim AS runtime

# Non-root user
RUN groupadd -r agent && useradd -r -g agent -d /app agent

WORKDIR /app

# Copy packages từ builder
COPY --from=builder /root/.local /home/agent/.local

# Copy application
COPY app/ ./app/
COPY utils/ ./utils/

RUN chown -R agent:agent /app

USER agent

ENV PATH=/home/agent/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ✅ FIX: thiếu dòng này container sẽ crash loop với
#   ModuleNotFoundError: No module named 'uvicorn'
#
# Nguyên nhân: user `agent` được tạo bằng `useradd ... -d /app`, tức HOME=/app.
# Python tự thêm "$HOME/.local/lib/python3.11/site-packages" vào sys.path,
# nghĩa là nó đi tìm ở /app/.local/... — nhưng packages lại được copy sang
# /home/agent/.local. Đường dẫn lệch nhau nên không import được gì.
#
# PYTHONUSERBASE chỉ đích danh nơi chứa package cho kiểu cài `pip install --user`.
# (Dockerfile của Part 5 có dòng này nên chạy được; Part 6 bị bỏ sót.)
ENV PYTHONUSERBASE=/home/agent/.local

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c \
    "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
    || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
