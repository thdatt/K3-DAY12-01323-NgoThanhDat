"""
CP1/CP3/CP4 — FastAPI app.

Luồng bảo vệ của /ask, xếp theo thứ tự rẻ trước đắt sau:

    1. verify_api_key       — sai/thiếu key → 401   (chỉ so chuỗi, gần như miễn phí)
    2. limiter.check        — quá tốc độ    → 429   (vài lệnh Redis)
    3. guard.check          — hết ngân sách → 402   (một lệnh Redis)
    4. ask_llm              — TỐN TIỀN, chỉ chạy khi đã qua cả 3 bước trên
    5. guard.record         — cộng chi phí thực tế vào Redis
"""
import time
from contextlib import asynccontextmanager

import redis
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import CostGuard
from app.lifecycle import lifecycle
from app.logging_utils import setup_logging
from app.rate_limiter import RateLimiter
from app.store import append_message, get_history, history_length, message_count
from utils.mock_llm import ask_llm

logger = setup_logging(settings.log_level)

# ── Redis + các thành phần phụ thuộc ──────────────────────────
# decode_responses=True → Redis trả str thay vì bytes, đỡ phải .decode() khắp nơi.
# socket_timeout để lệnh Redis không treo vô hạn khi mạng có sự cố.
redis_client = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=3,
    socket_timeout=3,
)

limiter = RateLimiter(redis_client, limit=settings.rate_limit_per_minute)
guard = CostGuard(redis_client, monthly_budget_usd=settings.monthly_budget_usd)


@asynccontextmanager
async def lifespan(app: FastAPI):
    lifecycle.install_signal_handlers()
    logger.info(
        "startup",
        extra={
            "port": settings.port,
            "rate_limit_per_minute": settings.rate_limit_per_minute,
            "monthly_budget_usd": settings.monthly_budget_usd,
        },
    )

    yield

    # Nhận tín hiệu tắt: ngừng nhận request mới, đợi request đang chạy xong,
    # rồi mới đóng kết nối Redis.
    await lifecycle.drain()
    try:
        redis_client.close()
        logger.info("redis_closed")
    except Exception as exc:
        logger.warning("redis_close_failed", extra={"error": str(exc)})
    logger.info("shutdown_complete")


app = FastAPI(title="Day 12 Production Agent", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def track_requests(request: Request, call_next):
    """
    Đếm số request đang xử lý để graceful shutdown biết khi nào chờ xong.

    Khối `finally` là bắt buộc: nếu request ném exception mà không giảm biến
    đếm, con số sẽ phình lên mãi và app không bao giờ chịu tắt.
    """
    lifecycle.enter_request()
    started = time.perf_counter()
    try:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        logger.info(
            "request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return response
    finally:
        lifecycle.exit_request()


# ── Models ────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)


# ── Endpoints ─────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "app": "Day 12 Production Agent",
        "endpoints": {
            "ask": "POST /ask (cần header X-API-Key)",
            "health": "GET /health",
            "ready": "GET /ready",
        },
    }


@app.get("/health")
def health():
    """
    Liveness — "Tôi còn sống".

    KHÔNG gọi Redis. Luôn trả 200 cho đến khi process tắt hẳn.

    Vì sao không trả 503 lúc đang tắt dần? Vì orchestrator sẽ tưởng container
    đã chết và giết tiến trình ngay lập tức, trước khi các request đang chạy
    kịp hoàn thành — đúng thứ mà graceful shutdown sinh ra để tránh.
    """
    return {
        "status": "ok",
        "uptime_seconds": lifecycle.uptime_seconds,
        "in_flight": lifecycle.in_flight,
        "shutting_down": lifecycle.is_shutting_down,
    }


@app.get("/ready")
def ready():
    """
    Readiness — "Tôi sẵn sàng nhận request".

    Trả 503 khi:
      - Đang trong quá trình tắt dần (báo Load Balancer ngắt traffic ngay), hoặc
      - Mất kết nối Redis (nhận request lúc này chỉ tạo ra lỗi 500)

    Trả 503 ở đây KHÔNG khiến container bị restart — chỉ tạm ngắt traffic.
    Redis khoẻ lại là tự động nhận request tiếp.
    """
    if lifecycle.is_shutting_down:
        return JSONResponse(
            status_code=503,
            content={"ready": False, "reason": "shutting_down"},
        )

    try:
        redis_client.ping()
    except Exception as exc:
        logger.warning("redis_unavailable", extra={"error": str(exc)})
        return JSONResponse(
            status_code=503,
            content={"ready": False, "reason": "redis_unavailable"},
        )

    return {"ready": True, "redis": "connected"}


@app.post("/ask")
def ask(
    body: AskRequest,
    _key: str = Depends(verify_api_key),
    x_user_id: str = Header(default="anonymous"),
):
    """
    Hỏi agent một câu. Yêu cầu header `X-API-Key`.

    Header `X-User-Id` xác định người dùng — dùng làm khoá cho rate limit,
    ngân sách và lịch sử hội thoại. Nhờ vậy hai user khác nhau có hạn mức
    riêng, không ảnh hưởng lẫn nhau.
    """
    user_id = x_user_id or "anonymous"

    # 1. Quá tốc độ? → 429
    limiter.check(user_id)

    # 2. Hết ngân sách? → 402 (kiểm tra TRƯỚC khi gọi LLM để không mất tiền oan)
    guard.check(user_id)

    # 3. Gọi LLM kèm lịch sử hội thoại làm ngữ cảnh
    history = get_history(redis_client, user_id)
    result = ask_llm(body.question, history=history)

    # 4. Ghi nhận chi phí THỰC TẾ sau khi có kết quả
    total_cost = guard.record(user_id, result["cost_usd"])

    # 5. Lưu hội thoại vào Redis để mọi instance đều đọc được
    append_message(redis_client, user_id, "user", body.question)
    append_message(redis_client, user_id, "assistant", result["answer"])

    logger.info(
        "ask_completed",
        extra={
            "user_id": user_id,
            "latency_ms": result["latency_ms"],
            "cost_usd": result["cost_usd"],
        },
    )

    return {
        "answer": result["answer"],
        "user_id": user_id,
        # history_length tăng đều 1, 2, 3, 4, 5 bất kể request rơi vào
        # container nào — bằng chứng thiết kế stateless hoạt động đúng.
        # (Đếm theo LƯỢT hội thoại; message_count là số message thô.)
        "history_length": history_length(redis_client, user_id),
        "message_count": message_count(redis_client, user_id),
        "usage": {
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "cost_usd": result["cost_usd"],
            "month_total_usd": round(total_cost, 6),
            "budget_usd": settings.monthly_budget_usd,
            "requests_remaining": limiter.remaining(user_id),
        },
    }


@app.get("/history")
def history(
    _key: str = Depends(verify_api_key),
    x_user_id: str = Header(default="anonymous"),
):
    """Xem lại lịch sử hội thoại của chính mình."""
    user_id = x_user_id or "anonymous"
    messages = get_history(redis_client, user_id)
    return {"user_id": user_id, "count": len(messages), "messages": messages}


@app.get("/usage")
def usage(
    _key: str = Depends(verify_api_key),
    x_user_id: str = Header(default="anonymous"),
):
    """Tình hình chi tiêu và hạn mức còn lại."""
    user_id = x_user_id or "anonymous"
    return {
        "user_id": user_id,
        "month_used_usd": round(guard.get_usage(user_id), 6),
        "month_budget_usd": settings.monthly_budget_usd,
        "month_remaining_usd": round(guard.remaining(user_id), 6),
        "rate_limit_per_minute": settings.rate_limit_per_minute,
        "requests_remaining": limiter.remaining(user_id),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        timeout_graceful_shutdown=30,
    )
