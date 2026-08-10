"""
CP3 — Rate limit bằng thuật toán Sliding Window trên Redis Sorted Set.

Quy trình xử lý mỗi request theo đúng thứ tự:
  1. Prune  — xoá các entry cũ hơn 60 giây (zremrangebyscore)
  2. Count  — đếm số entry còn lại (zcard)
  3. Check  — nếu >= limit → raise 429. Dừng ở đây, KHÔNG ghi nhận request bị chặn.
  4. Record — chỉ khi còn quota → ghi entry mới (zadd) với member duy nhất
  5. Expire — đặt TTL cho key để Redis tự dọn

Vì sao Sliding Window thay vì Fixed Window?
    Với Fixed Window (reset lúc giây 00), user có thể gửi 10 request ở giây 59
    và thêm 10 request ở giây 00 = 20 request trong 2 giây. Sliding Window
    ngăn chặn điều này vì nó luôn nhìn lại đúng 60 giây gần nhất.
"""
import time
import uuid

import redis
from fastapi import HTTPException

WINDOW_SECONDS = 60


class RateLimiter:
    def __init__(self, client: redis.Redis, limit: int = 10):
        """
        Args:
            client: Redis client dùng chung
            limit:  số request tối đa trong một cửa sổ 60 giây
        """
        self.client = client
        self.limit = limit

    def _key(self, user_id: str) -> str:
        return f"ratelimit:{user_id}"

    def check(self, user_id: str, now: float | None = None) -> None:
        """Cho qua nếu còn quota, ngược lại raise 429."""
        now = now if now is not None else time.time()
        key = self._key(user_id)

        # 1. Dọn entry cũ
        self.client.zremrangebyscore(key, 0, now - WINDOW_SECONDS)
        # 2. Đếm
        count = self.client.zcard(key)
        # 3. Vượt quota → chặn (KHÔNG ghi nhận request bị chặn)
        if count >= self.limit:
            raise HTTPException(
                status_code=429,
                detail="rate limit exceeded",
                headers={"Retry-After": str(WINDOW_SECONDS)},
            )
        # 4. Còn quota → ghi nhận (member duy nhất tránh ghi đè)
        self.client.zadd(key, {f"{now}:{uuid.uuid4().hex}": now})
        self.client.expire(key, WINDOW_SECONDS)

    def remaining(self, user_id: str, now: float | None = None) -> int:
        """Số request còn được phép trong cửa sổ hiện tại. Chỉ đọc."""
        now = now if now is not None else time.time()
        key = self._key(user_id)
        self.client.zremrangebyscore(key, 0, now - WINDOW_SECONDS)
        return max(0, self.limit - self.client.zcard(key))

    def reset(self, user_id: str) -> None:
        """Xoá bộ đếm của một user. Dùng cho test."""
        self.client.delete(self._key(user_id))


# ──────────────────────────────────────────────────────────────
# Vì sao member phải duy nhất?
#
# Nếu dùng str(now) làm member, hai request đến cùng mili-giây sẽ ghi đè nhau
# trong Sorted Set → đếm thiếu → rate limit bị "lọt". Dùng UUID đảm bảo mỗi
# request là một bản ghi riêng biệt.
#
# Ghi chú Production:
# Đoạn code trên minh hoạ thuật toán tuần tự. Trên production chịu tải lớn,
# các lệnh Redis cần gom vào một Lua script chạy atomic để tránh race
# condition giữa bước Count và bước Record.
# ──────────────────────────────────────────────────────────────
