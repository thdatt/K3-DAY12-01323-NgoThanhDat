"""
CP4 — Lịch sử hội thoại lưu trong Redis.

Thay vì lưu lịch sử chat trong dict Python (mất khi restart, không chia sẻ
giữa các container), lưu vào Redis List.

Vì sao bắt buộc? Load balancer chia request ngẫu nhiên:

    Request 1  ──> Instance A   (lưu history vào RAM của A)
    Request 2  ──> Instance B   (RAM của B trống → "bạn là ai?")
    Request 3  ──> Instance C   (RAM của C trống → quên tiếp)

Người dùng sẽ thấy agent mất trí nhớ ngẫu nhiên. Lỗi này cực khó debug vì
chạy 1 instance ở máy local thì không bao giờ tái hiện được.
"""
import json

import redis

# Giữ tối đa 40 message (20 lượt hỏi–đáp) để hội thoại dài không làm phình
# Redis và không vượt cửa sổ ngữ cảnh của LLM.
MAX_HISTORY = 40
HISTORY_TTL_SECONDS = 24 * 3600


def _key(user_id: str) -> str:
    return f"history:{user_id}"


def append_message(r: redis.Redis, user_id: str, role: str, content: str):
    """Thêm một message vào cuối lịch sử hội thoại của user."""
    key = f"history:{user_id}"
    message = json.dumps({"role": role, "content": content})
    r.rpush(key, message)
    # Cắt bớt phần cũ, chỉ giữ MAX_HISTORY message gần nhất
    r.ltrim(key, -MAX_HISTORY, -1)
    r.expire(key, HISTORY_TTL_SECONDS)


def get_history(r: redis.Redis, user_id: str) -> list:
    """Đọc toàn bộ lịch sử hội thoại của user."""
    key = f"history:{user_id}"
    return [json.loads(m) for m in r.lrange(key, 0, -1)]


def message_count(r: redis.Redis, user_id: str) -> int:
    """Tổng số message thô trong lịch sử (cả user lẫn assistant)."""
    return int(r.llen(_key(user_id)))


def history_length(r: redis.Redis, user_id: str) -> int:
    """
    Số LƯỢT hội thoại (mỗi lượt = 1 câu hỏi + 1 câu trả lời).

    Mỗi request lưu 2 message nên tổng số message tăng 2, 4, 6... Nhưng con
    số dễ hiểu với người dùng — và cũng là con số tài liệu lab yêu cầu quan
    sát — là số lượt: 1, 2, 3, 4, 5.

    Dùng số lượt thay vì số message cũng an toàn hơn khi sau này đổi cách
    lưu (ví dụ thêm message hệ thống): số lượt vẫn đúng ngữ nghĩa.
    """
    return sum(1 for m in get_history(r, user_id) if m.get("role") == "user")


def clear_history(r: redis.Redis, user_id: str) -> None:
    """Xoá lịch sử hội thoại của user. Dùng cho test."""
    r.delete(_key(user_id))
