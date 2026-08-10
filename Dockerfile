# ============================================================
# CP2 — Multi-stage build, image nhỏ gọn, chạy non-root
#
# Vấn đề: build 1 stage → image ~800MB-1GB (chứa cả compiler, pip cache,
#         build tools — những thứ chỉ cần lúc BUILD, không cần lúc CHẠY).
# Giải pháp: chia 2 stage, stage 2 chỉ copy kết quả đã cài xong.
# ============================================================

# ---- Stage 1: Builder ----
FROM python:3.11-slim AS builder

WORKDIR /build

# COPY requirements.txt TRƯỚC rồi mới pip install, sau đó mới COPY code.
# Docker cache theo layer: sửa code chỉ build lại layer code, còn layer
# pip install (chậm nhất) vẫn dùng cache. Nếu COPY . . lên trước thì sửa
# 1 dòng code cũng khiến pip install chạy lại từ đầu.
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ---- Stage 2: Production ----
FROM python:3.11-slim

WORKDIR /app

# Chỉ mang sang thư viện đã cài xong — không có pip cache, không có compiler
COPY --from=builder /install /usr/local

COPY app/ app/
COPY utils/ utils/

# Chạy dưới quyền user thường.
# Container mặc định chạy bằng root. Nếu có lỗ hổng trong code → kẻ tấn công
# có quyền root trong container → có thể leo thang ra máy host.
# USER appuser cắt đứt chuỗi tấn công đó.
RUN adduser --disabled-password --no-create-home appuser
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# Health check dùng Python (image slim không có curl, và phải đọc PORT động
# vì cloud platform cấp cổng ngẫu nhiên)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; port = os.getenv('PORT', '8000'); urllib.request.urlopen(f'http://127.0.0.1:{port}/health')" || exit 1

# Dùng shell form để expand biến $PORT khi chạy trên cloud.
# Viết ["uvicorn", "--port", "$PORT"] (exec form) sẽ truyền nguyên văn chuỗi
# "$PORT" cho uvicorn → lỗi 'not a valid integer'.
# `exec` để uvicorn thành PID 1, nhận trực tiếp SIGTERM từ Docker/cloud —
# thiếu nó thì sh giữ PID 1 và không chuyển tín hiệu xuống, graceful
# shutdown không bao giờ chạy.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
