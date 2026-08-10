"""
Cost Guard phiên bản Redis — lời giải cho Exercise 4.4

Vì sao cần bản này khi đã có `cost_guard.py`?
    `cost_guard.py` lưu chi tiêu trong dict Python (`self._records`), tức là
    trong RAM của **một tiến trình**. Khi scale lên nhiều instance, mỗi instance
    đếm riêng một sổ:

        Budget $10/tháng, chạy 3 instance
        → mỗi instance cho tiêu $10
        → thực tế tiêu $30 mới bị chặn

    Restart container cũng mất sạch số liệu → user được tiêu lại từ đầu.

    Redis là bộ nhớ dùng chung nằm ngoài tiến trình, nên mọi instance cùng đọc
    ghi một sổ duy nhất. Đây chính là nguyên tắc stateless của Part 5.

Yêu cầu đề bài (CODE_LAB.md Exercise 4.4):
    - Mỗi user có budget $10/tháng
    - Track spending trong Redis
    - Reset đầu tháng
"""
import os
from datetime import datetime, timezone

import redis
from fastapi import HTTPException

# ─────────────────────────────────────────────
# Config — đọc từ env, không hardcode (12-Factor)
# ─────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
MONTHLY_BUDGET_USD = float(os.getenv("MONTHLY_BUDGET_USD", "10.0"))
WARN_AT_PCT = 0.8

# decode_responses=True → Redis trả về str thay vì bytes, đỡ phải .decode()
r = redis.from_url(REDIS_URL, decode_responses=True)


def _month_key(user_id: str) -> str:
    """
    Sinh key dạng: budget:student:2026-08

    Nhét luôn tháng vào tên key là mẹo để "reset đầu tháng" xảy ra TỰ ĐỘNG:
    sang tháng mới, key đổi tên → Redis chưa có key đó → chi tiêu về 0.
    Không cần cron job, không cần lệnh xoá thủ công.
    """
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return f"budget:{user_id}:{month}"


def check_budget(user_id: str, estimated_cost: float = 0.0) -> bool:
    """
    Kiểm tra user còn budget không. KHÔNG ghi gì cả — chỉ đọc.

    Returns:
        True nếu còn budget.
    Raises:
        HTTPException 402 (Payment Required) nếu đã vượt.
    """
    key = _month_key(user_id)
    current = float(r.get(key) or 0.0)

    if current + estimated_cost > MONTHLY_BUDGET_USD:
        raise HTTPException(
            status_code=402,  # 402 Payment Required
            detail={
                "error": "Monthly budget exceeded",
                "used_usd": round(current, 6),
                "budget_usd": MONTHLY_BUDGET_USD,
                "resets_at": "đầu tháng sau (UTC)",
            },
        )
    return True


def record_cost(user_id: str, cost_usd: float) -> float:
    """
    Ghi nhận chi phí sau khi đã gọi LLM xong.

    Dùng INCRBYFLOAT thay vì GET rồi SET vì đây là thao tác **atomic**:
    Redis xử lý tuần tự từng lệnh, nên 3 instance cùng cộng tiền một lúc
    vẫn ra kết quả đúng. Nếu viết GET → cộng trong Python → SET thì sẽ dính
    race condition, hai instance đọc cùng giá trị cũ rồi ghi đè lẫn nhau,
    làm mất một phần chi phí.

    Returns:
        Tổng chi tiêu của tháng sau khi cộng.
    """
    key = _month_key(user_id)
    total = r.incrbyfloat(key, cost_usd)

    # TTL 32 ngày — lưới an toàn để key cũ tự biến mất, khỏi phình Redis.
    # Đặt lại mỗi lần ghi cũng không sao vì key đã gắn tháng trong tên.
    r.expire(key, 32 * 24 * 3600)

    return float(total)


def get_usage(user_id: str) -> dict:
    """Trả về tình hình chi tiêu tháng này của user."""
    key = _month_key(user_id)
    used = float(r.get(key) or 0.0)
    ttl = r.ttl(key)
    return {
        "user_id": user_id,
        "month": datetime.now(timezone.utc).strftime("%Y-%m"),
        "used_usd": round(used, 6),
        "budget_usd": MONTHLY_BUDGET_USD,
        "remaining_usd": round(max(0.0, MONTHLY_BUDGET_USD - used), 6),
        "used_pct": round(used / MONTHLY_BUDGET_USD * 100, 2),
        "near_limit": used >= MONTHLY_BUDGET_USD * WARN_AT_PCT,
        "key_expires_in_seconds": ttl if ttl > 0 else None,
    }


def reset_usage(user_id: str) -> bool:
    """Xoá chi tiêu của user trong tháng này. Chỉ dùng cho test/admin."""
    return bool(r.delete(_month_key(user_id)))


def ping() -> bool:
    """Kiểm tra Redis còn sống — dùng cho endpoint /ready."""
    try:
        return r.ping()
    except redis.RedisError:
        return False
