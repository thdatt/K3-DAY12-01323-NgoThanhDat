"""
Kết nối Redis dùng chung cho cả rate_limiter và cost_guard.

Tách ra file riêng để chỉ mở MỘT connection pool cho toàn app. Nếu mỗi
module tự gọi `redis.from_url()` thì sẽ có nhiều pool song song, tốn kết nối
và khó kiểm soát.

Thiết kế "có thì dùng, không có thì thôi":
    - Có REDIS_URL  → dùng Redis  → stateless, chạy được nhiều instance
    - Không có      → trả về None → module gọi tự chuyển sang bộ nhớ RAM

Nhờ vậy app vẫn chạy khi dev ở máy local không cài Redis, mà lên production
có Redis là tự động stateless.
"""
import logging

from app.config import settings

logger = logging.getLogger(__name__)

_client = None
_initialised = False


def get_redis():
    """
    Trả về Redis client, hoặc None nếu không dùng được.

    Kết nối được tạo một lần rồi tái sử dụng (lazy singleton). Lần đầu gọi
    mà lỗi thì ghi nhận luôn là không có Redis, các lần sau không thử lại
    nữa — tránh việc mỗi request đều chờ timeout kết nối.
    """
    global _client, _initialised

    if _initialised:
        return _client

    _initialised = True

    if not settings.redis_url:
        logger.warning(
            "REDIS_URL chưa được đặt — dùng bộ nhớ RAM. "
            "KHÔNG stateless: chạy nhiều instance sẽ cho số liệu sai."
        )
        _client = None
        return None

    try:
        import redis

        client = redis.from_url(
            settings.redis_url,
            decode_responses=True,      # trả str thay vì bytes
            socket_connect_timeout=3,   # đừng treo mãi khi Redis chết
            socket_timeout=3,
        )
        client.ping()
        logger.info("Đã kết nối Redis — chế độ stateless đang bật")
        _client = client
    except Exception as exc:
        logger.error(f"Không kết nối được Redis ({exc}) — quay về dùng RAM")
        _client = None

    return _client


def is_healthy() -> bool:
    """
    Redis có đang sống không? Dùng cho endpoint /ready.

    Không cấu hình Redis thì coi như khoẻ — vì lúc đó app cố tình chạy
    chế độ RAM, không phải là hỏng hóc.
    """
    client = get_redis()
    if client is None:
        return True
    try:
        return bool(client.ping())
    except Exception:
        return False


def reset_connection() -> None:
    """Buộc tạo lại kết nối ở lần gọi sau. Dùng cho test."""
    global _client, _initialised
    _client = None
    _initialised = False
