"""
Cấu hình chung cho pytest.

Đặt sẵn biến môi trường TRƯỚC khi import app, vì `app/config.py` đọc config
ngay lúc import và sẽ fail-fast nếu thiếu AGENT_API_KEY.
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TEST_API_KEY = "test-key-for-pytest-only"

os.environ.setdefault("AGENT_API_KEY", TEST_API_KEY)
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "10")
os.environ.setdefault("MONTHLY_BUDGET_USD", "10.0")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


def redis_available() -> bool:
    """Redis có đang chạy không? Test cần Redis sẽ tự bỏ qua nếu không có."""
    try:
        import redis
        redis.from_url(os.environ["REDIS_URL"], socket_connect_timeout=1).ping()
        return True
    except Exception:
        return False


needs_redis = pytest.mark.skipif(
    not redis_available(),
    reason="Cần Redis đang chạy: docker run -d -p 6379:6379 redis:7-alpine",
)


@pytest.fixture(scope="session")
def api_key() -> str:
    return os.environ["AGENT_API_KEY"]


@pytest.fixture
def client():
    """
    TestClient của FastAPI, dùng chung cho các test HTTP.

    `lifecycle` là singleton cấp module. Khi TestClient thoát khỏi context
    manager, nó chạy phần shutdown của lifespan → `begin_shutdown()` bật cờ
    `_shutting_down = True` và cờ đó CÒN NGUYÊN ở test tiếp theo, khiến mọi
    lời gọi /ready sau đó trả 503.

    Reset trạng thái ở cả trước lẫn sau mỗi test để các test độc lập nhau.
    """
    from fastapi.testclient import TestClient
    from app.lifecycle import lifecycle
    from app.main import app

    def reset():
        lifecycle._shutting_down = False
        lifecycle._in_flight = 0

    reset()
    with TestClient(app) as c:
        yield c
    reset()


@pytest.fixture
def rclient():
    """Redis client thô, để dọn dữ liệu test."""
    import redis
    r = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    yield r
    r.close()
