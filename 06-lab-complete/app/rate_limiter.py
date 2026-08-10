"""
Rate limiter — giới hạn số request mỗi phút.

Thuật toán: Sliding Window Log.
Lưu mốc thời gian của từng request, đếm số mốc còn nằm trong cửa sổ 60 giây.

Hai chế độ lưu trữ:
  - Có REDIS_URL  → dùng Redis  → STATELESS, nhiều instance dùng chung một sổ
  - Không có      → dùng RAM    → chỉ hợp cho chạy local một mình

Vì sao Redis quan trọng? Với bộ đếm trong RAM, chạy 3 instance nghĩa là mỗi
instance có sổ riêng, nên giới hạn 20 req/phút thực tế thành 60 req/phút.
Restart container cũng xoá sạch bộ đếm, kẻ tấn công chỉ cần chờ deploy là
được reset.
"""
import time
from collections import defaultdict, deque

from fastapi import HTTPException

from app.config import settings
from app.storage import get_redis

WINDOW_SECONDS = 60

# Bộ đếm dự phòng trong RAM khi không có Redis
_memory_windows: dict[str, deque] = defaultdict(deque)


def _check_redis(key: str, limit: int) -> dict:
    """
    Sliding window bằng Redis Sorted Set.

    Mỗi request là một phần tử trong ZSET, dùng timestamp làm score.
    Cả 4 lệnh gói trong một pipeline để Redis chạy liền mạch, tránh việc
    hai instance xen kẽ nhau làm sai kết quả đếm.
    """
    r = get_redis()
    now = time.time()
    redis_key = f"ratelimit:{key}"

    pipe = r.pipeline()
    pipe.zremrangebyscore(redis_key, 0, now - WINDOW_SECONDS)  # xoá mốc đã cũ
    pipe.zcard(redis_key)                                       # đếm còn lại
    pipe.zadd(redis_key, {f"{now}:{id(now)}": now})             # ghi mốc mới
    pipe.expire(redis_key, WINDOW_SECONDS + 10)                 # tự dọn rác
    _, count_before, _, _ = pipe.execute()

    if count_before >= limit:
        # Đã ghi mốc mới ở trên rồi, giờ phải gỡ ra vì request này bị từ chối
        r.zremrangebyscore(redis_key, now, now)
        oldest = r.zrange(redis_key, 0, 0, withscores=True)
        retry_after = int(oldest[0][1] + WINDOW_SECONDS - now) + 1 if oldest else WINDOW_SECONDS
        _raise_429(limit, retry_after)

    return {"limit": limit, "remaining": limit - count_before - 1}


def _check_memory(key: str, limit: int) -> dict:
    """Sliding window bằng deque trong RAM — chỉ dùng khi không có Redis."""
    now = time.time()
    window = _memory_windows[key]

    while window and window[0] < now - WINDOW_SECONDS:
        window.popleft()

    if len(window) >= limit:
        retry_after = int(window[0] + WINDOW_SECONDS - now) + 1
        _raise_429(limit, retry_after)

    window.append(now)
    return {"limit": limit, "remaining": limit - len(window)}


def _raise_429(limit: int, retry_after: int) -> None:
    raise HTTPException(
        status_code=429,
        detail={
            "error": "Rate limit exceeded",
            "limit": limit,
            "window_seconds": WINDOW_SECONDS,
            "retry_after_seconds": retry_after,
        },
        # Các header này là chuẩn chung, client tử tế sẽ đọc và tự chờ
        headers={
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": "0",
            "Retry-After": str(retry_after),
        },
    )


def check_rate_limit(key: str, limit: int | None = None) -> dict:
    """
    Kiểm tra và ghi nhận một request.

    Args:
        key: định danh người gọi (xem `auth.key_identity`)
        limit: số request tối đa mỗi phút; None = lấy từ config

    Returns:
        dict gồm `limit` và `remaining`.

    Raises:
        HTTPException 429 nếu vượt giới hạn.
    """
    limit = limit if limit is not None else settings.rate_limit_per_minute
    r = get_redis()
    return _check_redis(key, limit) if r else _check_memory(key, limit)


def reset(key: str) -> None:
    """Xoá bộ đếm của một key. Dùng cho test."""
    r = get_redis()
    if r:
        r.delete(f"ratelimit:{key}")
    _memory_windows.pop(key, None)
