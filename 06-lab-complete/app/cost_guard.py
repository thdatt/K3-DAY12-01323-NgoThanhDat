"""
Cost guard — chặn hoá đơn LLM vượt ngân sách.

Vấn đề có thật: API công khai + LLM tính tiền theo token = một vòng lặp lỗi
của client, hoặc một kẻ phá hoại, có thể đốt hàng nghìn đô trong một đêm.

Cách bảo vệ hai tầng:
    1. Ngân sách theo từng user  → một người không thể ăn hết phần cả nhà
    2. Ngân sách toàn hệ thống   → trần cứng cho toàn bộ dịch vụ

Lưu trong Redis khi có, để nhiều instance cùng đếm chung một sổ.
"""
import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config import settings
from app.storage import get_redis

logger = logging.getLogger(__name__)

# Đơn giá tham khảo của gpt-4o-mini (USD cho mỗi 1000 token)
PRICE_PER_1K_INPUT = 0.00015
PRICE_PER_1K_OUTPUT = 0.0006

WARN_AT_PCT = 0.8          # ghi cảnh báo khi dùng tới 80% ngân sách
KEY_TTL_SECONDS = 3 * 24 * 3600

# Sổ dự phòng trong RAM khi không có Redis
_memory_costs: dict[str, float] = {}


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Quy đổi số token thành tiền USD."""
    return (input_tokens / 1000) * PRICE_PER_1K_INPUT + \
           (output_tokens / 1000) * PRICE_PER_1K_OUTPUT


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _user_key(identity: str) -> str:
    """
    Khoá dạng: cost:user:abc12345:2026-08-10

    Nhét ngày vào tên khoá để việc "reset mỗi ngày" tự xảy ra: sang ngày mới,
    tên khoá đổi, Redis chưa có khoá đó nên chi tiêu về 0. Không cần cron job.
    """
    return f"cost:user:{identity}:{_today()}"


def _global_key() -> str:
    return f"cost:global:{_today()}"


def _get(key: str) -> float:
    r = get_redis()
    if r:
        return float(r.get(key) or 0.0)
    return _memory_costs.get(key, 0.0)


def _incr(key: str, amount: float) -> float:
    r = get_redis()
    if r:
        # INCRBYFLOAT là thao tác atomic — nhiều instance cùng cộng tiền vẫn
        # ra đúng tổng. Kiểu đọc-rồi-ghi (GET → tính → SET) sẽ dính race
        # condition, hai instance đọc cùng số cũ rồi ghi đè nhau, mất tiền.
        total = float(r.incrbyfloat(key, amount))
        r.expire(key, KEY_TTL_SECONDS)
        return total
    _memory_costs[key] = _memory_costs.get(key, 0.0) + amount
    return _memory_costs[key]


def check_budget(identity: str, estimated: float = 0.0) -> None:
    """
    Kiểm tra TRƯỚC khi gọi LLM. Chỉ đọc, không ghi gì.

    Raises:
        503 nếu ngân sách toàn hệ thống đã cạn (lỗi phía dịch vụ)
        402 nếu ngân sách của riêng user đã cạn (lỗi phía người dùng)
    """
    # Trần cứng toàn hệ thống — kiểm tra trước vì nghiêm trọng hơn
    global_used = _get(_global_key())
    if global_used >= settings.global_daily_budget_usd:
        logger.critical(f"Ngân sách toàn hệ thống đã cạn: ${global_used:.4f}")
        raise HTTPException(
            status_code=503,
            detail="Service tạm ngưng do đã chạm trần ngân sách. Thử lại vào ngày mai.",
        )

    used = _get(_user_key(identity))
    if used + estimated > settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,  # 402 Payment Required — đúng nghĩa "hết tiền"
            detail={
                "error": "Daily budget exceeded",
                "used_usd": round(used, 6),
                "budget_usd": settings.daily_budget_usd,
                "resets_at": "00:00 UTC",
            },
        )

    if used >= settings.daily_budget_usd * WARN_AT_PCT:
        logger.warning(
            f"User {identity} đã dùng {used / settings.daily_budget_usd * 100:.0f}% ngân sách"
        )


def record_cost(identity: str, input_tokens: int, output_tokens: int) -> float:
    """
    Ghi nhận chi phí SAU khi gọi LLM xong.

    Tách khỏi check_budget() để nếu LLM lỗi giữa chừng thì user không bị
    trừ tiền oan.

    Returns:
        Tổng chi tiêu trong ngày của user sau khi cộng.
    """
    cost = estimate_cost(input_tokens, output_tokens)
    _incr(_global_key(), cost)
    return _incr(_user_key(identity), cost)


def get_usage(identity: str) -> dict:
    """Tình hình chi tiêu hôm nay."""
    used = _get(_user_key(identity))
    budget = settings.daily_budget_usd
    return {
        "date": _today(),
        "used_usd": round(used, 6),
        "budget_usd": budget,
        "remaining_usd": round(max(0.0, budget - used), 6),
        "used_pct": round(used / budget * 100, 2) if budget else 0.0,
        "global_used_usd": round(_get(_global_key()), 6),
        "global_budget_usd": settings.global_daily_budget_usd,
        "storage": "redis" if get_redis() else "memory",
    }


def reset(identity: str) -> None:
    """Xoá chi tiêu của user hôm nay. Dùng cho test."""
    r = get_redis()
    if r:
        r.delete(_user_key(identity), _global_key())
    _memory_costs.pop(_user_key(identity), None)
    _memory_costs.pop(_global_key(), None)
