"""
Production AI Agent — Kết hợp tất cả Day 12 concepts

Checklist:
  ✅ Config từ environment (12-factor)     — app/config.py
  ✅ Structured JSON logging
  ✅ API Key authentication                — app/auth.py
  ✅ Rate limiting (Redis, stateless)      — app/rate_limiter.py
  ✅ Cost guard (Redis, stateless)         — app/cost_guard.py
  ✅ Input validation (Pydantic)
  ✅ Health check + Readiness probe
  ✅ Graceful shutdown
  ✅ Security headers
  ✅ CORS
  ✅ Error handling

Cấu trúc module tách theo đúng yêu cầu của DAY12_DELIVERY_CHECKLIST.md.
main.py chỉ còn lo phần HTTP; mọi logic nghiệp vụ nằm ở module riêng, dễ
đọc và test độc lập.
"""
import os
import time
import signal
import logging
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from app.config import settings
from app.auth import verify_api_key, key_identity
from app.rate_limiter import check_rate_limit
from app import cost_guard
from app import storage

# Mock LLM (thay bằng OpenAI/Anthropic khi có API key)
from utils.mock_llm import ask as llm_ask


# ─────────────────────────────────────────────────────────
# Logging — JSON structured
# ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
    # ✅ force=True: ép ghi đè nếu thư viện nào đó đã lỡ cấu hình root logger
    # trước ta. Thiếu dòng này, basicConfig() im lặng không làm gì và toàn bộ
    # log JSON biến mất.
    force=True,
)
logger = logging.getLogger(__name__)

# ✅ Log cảnh báo config SAU khi logging đã cấu hình xong, để chúng cũng
# ra đúng định dạng JSON như mọi dòng log khác.
for _warning in settings.startup_warnings:
    logger.warning(_warning)

START_TIME = time.time()
_is_ready = False
_request_count = 0
_error_count = 0


# ─────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready

    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "storage": "redis" if storage.get_redis() else "memory",
        "rate_limit_per_minute": settings.rate_limit_per_minute,
        "daily_budget_usd": settings.daily_budget_usd,
    }))

    _is_ready = True
    logger.info(json.dumps({"event": "ready"}))

    yield

    # ── Shutdown ──
    # Đặt _is_ready = False TRƯỚC tiên để /ready trả 503 ngay lập tức.
    # Load balancer thấy vậy sẽ ngừng gửi request mới vào instance này,
    # trong khi request đang dở vẫn được xử lý nốt. Đây là điều kiện để
    # deploy không downtime.
    _is_ready = False
    logger.info(json.dumps({"event": "shutdown", "served": _request_count}))


# ─────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    # Tắt /docs trên production: sơ đồ API công khai giúp kẻ tấn công
    # dò endpoint dễ hơn nhiều.
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    start = time.time()
    _request_count += 1
    try:
        response: Response = await call_next(request)
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        # ✅ FIX: code cũ viết `response.headers.pop("server", None)` khiến
        # MỌI request trả về 500.
        # `response.headers` là đối tượng MutableHeaders của Starlette — nó
        # kế thừa Mapping (chỉ đọc) chứ không phải MutableMapping, nên không
        # hề có method .pop(). Phải dùng `del` và tự kiểm tra key tồn tại,
        # vì `del` sẽ ném KeyError nếu header không có.
        if "server" in response.headers:
            del response.headers["server"]
        duration = round((time.time() - start) * 1000, 1)
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration,
        }))
        return response
    except Exception:
        _error_count += 1
        raise


# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000,
                          description="Your question for the agent")


class AskResponse(BaseModel):
    question: str
    answer: str
    model: str
    timestamp: str
    usage: dict


# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────

@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "endpoints": {
            "ask": "POST /ask (requires X-API-Key)",
            "health": "GET /health",
            "ready": "GET /ready",
            "metrics": "GET /metrics (requires X-API-Key)",
        },
    }


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(
    body: AskRequest,
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    """
    Gửi câu hỏi cho agent.

    **Authentication:** header `X-API-Key: <your-key>`

    Thứ tự bảo vệ — rẻ trước, đắt sau:
        1. Xác thực    (Depends, trước cả khi vào hàm)
        2. Rate limit  (một lệnh Redis)
        3. Budget      (một lệnh Redis)
        4. Gọi LLM     (tốn tiền — chỉ tới đây khi đã qua hết 3 bước trên)
    """
    identity = key_identity(api_key)

    rate_info = check_rate_limit(identity)

    # Ước lượng chi phí đầu vào rồi kiểm tra ngân sách TRƯỚC khi gọi LLM
    input_tokens = len(body.question.split()) * 2
    estimated = cost_guard.estimate_cost(input_tokens, 0)
    cost_guard.check_budget(identity, estimated)

    logger.info(json.dumps({
        "event": "agent_call",
        "q_len": len(body.question),
        "client": str(request.client.host) if request.client else "unknown",
    }))

    answer = llm_ask(body.question)

    # Ghi nhận chi phí thật SAU khi có kết quả — LLM lỗi thì không bị trừ oan
    output_tokens = len(answer.split()) * 2
    total_used = cost_guard.record_cost(identity, input_tokens, output_tokens)

    return AskResponse(
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        timestamp=datetime.now(timezone.utc).isoformat(),
        usage={
            "requests_remaining": rate_info["remaining"],
            "budget_used_usd": round(total_used, 6),
            "budget_remaining_usd": round(
                max(0.0, settings.daily_budget_usd - total_used), 6
            ),
        },
    )


@app.get("/health", tags=["Operations"])
def health():
    """
    Liveness probe — "tiến trình còn sống không?"

    CỐ Ý không kiểm tra Redis ở đây. Nếu có, một sự cố Redis thoáng qua sẽ
    khiến platform restart ĐỒNG LOẠT mọi container — biến sự cố nhỏ ở tầng
    cache thành sập toàn hệ thống. Việc kiểm tra dependency là của /ready.
    """
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "checks": {"llm": "mock" if not settings.openai_api_key else "openai"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    """
    Readiness probe — "nhận request được chưa?"

    ĐÂY mới là chỗ kiểm tra dependency. Trả 503 thì load balancer ngừng gửi
    traffic vào instance này, nhưng KHÔNG restart nó — chờ Redis khoẻ lại là
    tự động nhận traffic tiếp.
    """
    if not _is_ready:
        raise HTTPException(503, "Not ready — đang khởi động hoặc đang tắt")

    if not storage.is_healthy():
        raise HTTPException(503, "Not ready — mất kết nối Redis")

    return {
        "ready": True,
        "storage": "redis" if storage.get_redis() else "memory",
    }


@app.get("/metrics", tags=["Operations"])
def metrics(api_key: str = Depends(verify_api_key)):
    """Số liệu vận hành (có bảo vệ bằng API key)."""
    usage = cost_guard.get_usage(key_identity(api_key))
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "rate_limit_per_minute": settings.rate_limit_per_minute,
        **usage,
    }


# ─────────────────────────────────────────────────────────
# Graceful Shutdown
# ─────────────────────────────────────────────────────────
def _handle_signal(signum, frame):
    """
    Ghi log thời điểm nhận tín hiệu, RỒI trả quyền lại cho uvicorn.

    ✅ FIX — đây là bug tinh vi nhất của cả lab.

    Code cũ viết:

        def _handle_signal(signum, _frame):
            logger.info(...)          # chỉ ghi log rồi thôi

        signal.signal(signal.SIGTERM, _handle_signal)

    Hàm này ghi đè handler SIGTERM của uvicorn nhưng **không làm gì tiếp**.
    Kết quả ngược hoàn toàn với ý định: app nhận SIGTERM, ghi log, rồi
    **chạy tiếp như chưa có gì xảy ra**. Docker chờ hết 10 giây rồi buộc
    phải SIGKILL — tức là giết cứng, đúng thứ mà "graceful shutdown" sinh ra
    để tránh.

    Đo thực tế: `docker stop` mất 10,4 giây (chờ hết timeout) thay vì ~1 giây.

    Cách sửa: lưu lại handler cũ trước khi ghi đè, ghi log xong thì gọi tiếp
    handler cũ để uvicorn chạy phần shutdown của lifespan như bình thường.
    """
    logger.info(json.dumps({"event": "signal", "signum": signum}))

    if callable(_previous_sigterm):
        _previous_sigterm(signum, frame)
    else:
        # Handler cũ là SIG_DFL/SIG_IGN (không gọi trực tiếp được):
        # trả handler về mặc định rồi tự gửi lại tín hiệu cho chính mình.
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGTERM)


_previous_sigterm = signal.getsignal(signal.SIGTERM)
signal.signal(signal.SIGTERM, _handle_signal)


if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    logger.info(f"API Key: {settings.agent_api_key[:4]}****")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
