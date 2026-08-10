"""CP3 — API Security: Auth, Rate Limit & Cost Guard."""
import time
import uuid

import pytest
from fastapi import HTTPException

from conftest import needs_redis

BODY = {"question": "Xin chao"}


# ── 3.1 Xác thực API Key ──────────────────────────────────────
@needs_redis
def test_thieu_api_key_tra_401(client):
    assert client.post("/ask", json=BODY).status_code == 401


@needs_redis
def test_sai_api_key_tra_401(client):
    r = client.post("/ask", json=BODY, headers={"X-API-Key": "sai-hoan-toan"})
    assert r.status_code == 401


@needs_redis
def test_dung_api_key_tra_200(client, api_key, rclient):
    uid = f"t-{uuid.uuid4().hex[:8]}"
    r = client.post("/ask", json=BODY,
                    headers={"X-API-Key": api_key, "X-User-Id": uid})
    assert r.status_code == 200
    assert "answer" in r.json()


@needs_redis
def test_health_va_ready_la_public(client):
    """Platform phải gọi được health check mà không cần key."""
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200


def test_so_sanh_key_chong_timing_attack():
    """
    Phải dùng hmac.compare_digest, không dùng `==`.

    `==` thoát ra ngay khi gặp ký tự khác nhau đầu tiên, nên thời gian phản
    hồi tiết lộ khớp được bao nhiêu ký tự đầu — kẻ tấn công đo đủ nhiều lần
    có thể dò ra key từng ký tự một.
    """
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "app" / "auth.py").read_text(encoding="utf-8")
    assert "compare_digest" in src


# ── 3.2 Rate limit — Sliding Window ───────────────────────────
@needs_redis
def test_rate_limit_chan_dung_nguong(rclient):
    from app.rate_limiter import RateLimiter

    uid = f"rl-{uuid.uuid4().hex[:8]}"
    limiter = RateLimiter(rclient, limit=5)
    limiter.reset(uid)

    for _ in range(5):
        limiter.check(uid)                    # 5 lần đầu phải qua

    with pytest.raises(HTTPException) as exc:
        limiter.check(uid)                    # lần thứ 6 phải bị chặn
    assert exc.value.status_code == 429
    limiter.reset(uid)


@needs_redis
def test_request_bi_chan_KHONG_duoc_ghi_nhan(rclient):
    """
    Bước 3 phải dừng TRƯỚC bước 4 (zadd).

    Nếu vẫn ghi nhận request đã bị chặn, user bị spam sẽ không bao giờ thoát
    khỏi trạng thái 429 vì cửa sổ liên tục được làm mới.
    """
    from app.rate_limiter import RateLimiter

    uid = f"rl-{uuid.uuid4().hex[:8]}"
    limiter = RateLimiter(rclient, limit=3)
    limiter.reset(uid)

    for _ in range(3):
        limiter.check(uid)

    truoc = rclient.zcard(f"ratelimit:{uid}")
    for _ in range(5):
        with pytest.raises(HTTPException):
            limiter.check(uid)
    sau = rclient.zcard(f"ratelimit:{uid}")

    assert truoc == sau == 3
    limiter.reset(uid)


@needs_redis
def test_sliding_window_nha_quota_khi_entry_cu_het_han(rclient):
    """Cửa sổ TRƯỢT: entry cũ hơn 60 giây bị loại, quota được nhả ra."""
    from app.rate_limiter import RateLimiter

    uid = f"rl-{uuid.uuid4().hex[:8]}"
    limiter = RateLimiter(rclient, limit=2)
    limiter.reset(uid)

    now = time.time()
    limiter.check(uid, now=now - 120)     # 2 phút trước — đã ra ngoài cửa sổ
    limiter.check(uid, now=now - 90)
    limiter.check(uid, now=now)           # phải qua được vì 2 entry kia hết hạn
    limiter.reset(uid)


@needs_redis
def test_member_duy_nhat_khong_bi_ghi_de(rclient):
    """
    Hai request cùng mili-giây phải là 2 bản ghi riêng.

    Dùng str(now) làm member thì chúng ghi đè nhau trong Sorted Set → đếm
    thiếu → rate limit bị "lọt".
    """
    from app.rate_limiter import RateLimiter

    uid = f"rl-{uuid.uuid4().hex[:8]}"
    limiter = RateLimiter(rclient, limit=10)
    limiter.reset(uid)

    now = time.time()
    limiter.check(uid, now=now)
    limiter.check(uid, now=now)           # y hệt timestamp

    assert rclient.zcard(f"ratelimit:{uid}") == 2
    limiter.reset(uid)


@needs_redis
def test_rate_limit_qua_http(client, api_key, rclient):
    from app.config import settings

    uid = f"rl-{uuid.uuid4().hex[:8]}"
    rclient.delete(f"ratelimit:{uid}")
    headers = {"X-API-Key": api_key, "X-User-Id": uid}

    codes = [client.post("/ask", json=BODY, headers=headers).status_code
             for _ in range(settings.rate_limit_per_minute + 3)]

    assert codes.count(200) == settings.rate_limit_per_minute
    assert codes.count(429) == 3
    rclient.delete(f"ratelimit:{uid}")


# ── 3.3 Cost Guard ────────────────────────────────────────────
@needs_redis
def test_cost_guard_chan_bang_402(rclient):
    from app.cost_guard import CostGuard

    uid = f"cg-{uuid.uuid4().hex[:8]}"
    guard = CostGuard(rclient, monthly_budget_usd=1.0)
    guard.reset(uid)

    guard.check(uid)                      # chưa tiêu gì → qua
    guard.record(uid, 1.5)                # vượt ngân sách

    with pytest.raises(HTTPException) as exc:
        guard.check(uid)
    assert exc.value.status_code == 402   # 402 Payment Required
    guard.reset(uid)


@needs_redis
def test_cost_guard_cong_don_dung(rclient):
    from app.cost_guard import CostGuard

    uid = f"cg-{uuid.uuid4().hex[:8]}"
    guard = CostGuard(rclient, monthly_budget_usd=10.0)
    guard.reset(uid)

    guard.record(uid, 2.5)
    guard.record(uid, 3.0)
    total = guard.record(uid, 1.5)

    assert abs(total - 7.0) < 1e-6
    assert abs(guard.remaining(uid) - 3.0) < 1e-6
    guard.reset(uid)


@needs_redis
def test_key_gan_thang_de_tu_reset(rclient):
    """
    Khoá dạng cost:<user>:<YYYY-MM>. Sang tháng mới tên khoá đổi → Redis
    chưa có → chi tiêu về 0. Không cần cron job dọn dẹp.
    """
    from datetime import datetime, timezone
    from app.cost_guard import CostGuard

    guard = CostGuard(rclient, monthly_budget_usd=10.0)
    key = guard._key("sv01")
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    assert key == f"cost:sv01:{month}"


@needs_redis
def test_du_lieu_nam_trong_redis_khong_phai_RAM(rclient):
    """Bằng chứng stateless: đọc thẳng từ Redis vẫn thấy số liệu."""
    from app.cost_guard import CostGuard

    uid = f"cg-{uuid.uuid4().hex[:8]}"
    guard = CostGuard(rclient, monthly_budget_usd=10.0)
    guard.reset(uid)
    guard.record(uid, 4.2)

    assert abs(float(rclient.get(guard._key(uid))) - 4.2) < 1e-6
    guard.reset(uid)
