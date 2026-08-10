"""
CP3 — Cost Guard: chặn hoá đơn LLM vượt ngân sách.

Mỗi lần gọi mock LLM → tính chi phí (token × giá). Tích luỹ theo tháng trong
Redis key `cost:<user_id>:<YYYY-MM>`. Vượt `monthly_budget_usd` → trả 402.

Cơ chế Pre-check + Post-record (Soft Quota):
    1. guard.check(user_id)                    — tổng chi phí đã vượt budget chưa? Rồi → 402
    2. result = ask_llm(...)                   — gọi LLM, nhận response + chi phí thực tế
    3. guard.record(user_id, result["cost_usd"]) — cộng dồn chi phí thực tế vào Redis

Điều này nghĩa là tổng chi phí có thể vượt budget tối đa bằng chi phí của
đúng 1 request cuối cùng (soft quota). Đây là trade-off có chủ đích: chặn
trước khi gọi LLM để không mất tiền oan, nhưng không thể biết chính xác chi
phí trước khi gọi.

Rate Limit vs Cost Guard:
  - Rate limit chặn user gửi request nhanh quá (bảo vệ hạ tầng).
  - Cost guard chặn user tiêu tiền nhiều quá (bảo vệ ngân sách).
  - Tình huống rate limit cho qua nhưng cost guard chặn: user gửi 1
    request/phút (không vi phạm tốc độ) nhưng mỗi request xử lý file 100
    trang (tốn rất nhiều token).
"""
from datetime import datetime, timezone

import redis
from fastapi import HTTPException

# TTL 63 ngày — đủ dài để dữ liệu tháng trước còn tra cứu được, đủ ngắn để
# Redis không phình vô hạn.
KEY_TTL_SECONDS = 63 * 24 * 3600


class CostGuard:
    def __init__(self, client: redis.Redis, monthly_budget_usd: float = 10.0):
        self.client = client
        self.monthly_budget_usd = monthly_budget_usd

    def _key(self, user_id: str) -> str:
        """
        Khoá dạng: cost:sv01:2026-08

        Nhét tháng vào tên khoá là mẹo để việc "reset đầu tháng" xảy ra TỰ
        ĐỘNG: sang tháng mới, tên khoá đổi, Redis chưa có khoá đó nên chi
        tiêu về 0. Không cần cron job, không cần lệnh xoá thủ công.
        """
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        return f"cost:{user_id}:{month}"

    def get_usage(self, user_id: str) -> float:
        """Tổng chi phí đã dùng trong tháng này (USD)."""
        return float(self.client.get(self._key(user_id)) or 0.0)

    def check(self, user_id: str) -> None:
        """
        Kiểm tra TRƯỚC khi gọi LLM. Chỉ đọc, không ghi.

        Raises:
            HTTPException 402 Payment Required khi đã vượt ngân sách tháng.
        """
        used = self.get_usage(user_id)
        if used >= self.monthly_budget_usd:
            raise HTTPException(
                status_code=402,  # 402 Payment Required — đúng nghĩa "hết tiền"
                detail={
                    "error": "monthly budget exceeded",
                    "used_usd": round(used, 6),
                    "budget_usd": self.monthly_budget_usd,
                    "resets_at": "đầu tháng sau (UTC)",
                },
            )

    def record(self, user_id: str, cost_usd: float) -> float:
        """
        Ghi nhận chi phí SAU khi gọi LLM xong.

        Dùng INCRBYFLOAT thay vì GET → cộng → SET vì đây là thao tác atomic:
        Redis xử lý tuần tự từng lệnh, nên nhiều instance cùng cộng tiền một
        lúc vẫn ra đúng tổng. Kiểu đọc-rồi-ghi sẽ dính race condition, hai
        instance đọc cùng giá trị cũ rồi ghi đè nhau làm mất tiền.

        Returns:
            Tổng chi phí của tháng sau khi cộng.
        """
        key = self._key(user_id)
        total = float(self.client.incrbyfloat(key, cost_usd))
        self.client.expire(key, KEY_TTL_SECONDS)
        return total

    def remaining(self, user_id: str) -> float:
        """Ngân sách còn lại trong tháng (USD)."""
        return max(0.0, self.monthly_budget_usd - self.get_usage(user_id))

    def reset(self, user_id: str) -> None:
        """Xoá chi tiêu tháng này của user. Dùng cho test."""
        self.client.delete(self._key(user_id))
