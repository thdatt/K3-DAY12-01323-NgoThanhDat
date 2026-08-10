"""CP4 — Scaling & Reliability: stateless store + graceful shutdown."""
import uuid

import pytest

from conftest import needs_redis

BODY = {"question": "Xin chao"}


# ── 4.1 Lịch sử hội thoại trong Redis ─────────────────────────
@needs_redis
def test_luu_va_doc_lai_duoc_lich_su(rclient):
    from app.store import append_message, clear_history, get_history

    uid = f"st-{uuid.uuid4().hex[:8]}"
    clear_history(rclient, uid)

    append_message(rclient, uid, "user", "Xin chao")
    append_message(rclient, uid, "assistant", "Chao ban")

    history = get_history(rclient, uid)
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "Xin chao"}
    assert history[1]["role"] == "assistant"
    clear_history(rclient, uid)


@needs_redis
def test_state_nam_trong_redis_khong_phai_dict_python(rclient):
    """
    Bằng chứng stateless: một client Redis KHÁC vẫn đọc được dữ liệu.

    Nếu lưu trong dict Python thì client khác (tương đương container khác)
    sẽ không thấy gì.
    """
    import os
    import redis
    from app.store import append_message, clear_history, get_history

    uid = f"st-{uuid.uuid4().hex[:8]}"
    clear_history(rclient, uid)
    append_message(rclient, uid, "user", "tin nhan tu client 1")

    other = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    try:
        assert len(get_history(other, uid)) == 1
    finally:
        other.close()
        clear_history(rclient, uid)


@needs_redis
def test_history_length_dem_theo_luot(rclient):
    """history_length phải tăng 1, 2, 3... mỗi lượt hỏi–đáp."""
    from app.store import append_message, clear_history, history_length

    uid = f"st-{uuid.uuid4().hex[:8]}"
    clear_history(rclient, uid)

    for i in range(1, 4):
        append_message(rclient, uid, "user", f"cau hoi {i}")
        append_message(rclient, uid, "assistant", f"tra loi {i}")
        assert history_length(rclient, uid) == i

    clear_history(rclient, uid)


@needs_redis
def test_history_length_tang_deu_qua_http(client, api_key, rclient):
    """Mô phỏng đúng kịch bản kiểm tra stateless của lab."""
    uid = f"st-{uuid.uuid4().hex[:8]}"
    rclient.delete(f"history:{uid}", f"ratelimit:{uid}")
    headers = {"X-API-Key": api_key, "X-User-Id": uid}

    lengths = []
    for i in range(1, 6):
        r = client.post("/ask", json={"question": f"Xin chao lan {i}"}, headers=headers)
        assert r.status_code == 200
        lengths.append(r.json()["history_length"])

    assert lengths == [1, 2, 3, 4, 5]
    rclient.delete(f"history:{uid}", f"ratelimit:{uid}")


@needs_redis
def test_hai_user_khong_lan_lich_su(rclient):
    from app.store import append_message, clear_history, get_history

    a, b = f"u-{uuid.uuid4().hex[:6]}", f"u-{uuid.uuid4().hex[:6]}"
    clear_history(rclient, a)
    clear_history(rclient, b)

    append_message(rclient, a, "user", "cua A")
    assert len(get_history(rclient, a)) == 1
    assert len(get_history(rclient, b)) == 0

    clear_history(rclient, a)
    clear_history(rclient, b)


# ── 4.2 Graceful shutdown ─────────────────────────────────────
def test_lifecycle_dem_request_dang_chay():
    from app.lifecycle import Lifecycle

    lc = Lifecycle()
    assert lc.in_flight == 0
    lc.enter_request()
    lc.enter_request()
    assert lc.in_flight == 2
    lc.exit_request()
    assert lc.in_flight == 1


def test_bien_dem_khong_tut_xuong_am():
    """Phòng trường hợp middleware gọi lệch nhịp, tránh kẹt vòng chờ mãi mãi."""
    from app.lifecycle import Lifecycle

    lc = Lifecycle()
    lc.exit_request()
    lc.exit_request()
    assert lc.in_flight == 0


def test_begin_shutdown_lam_ready_tra_false():
    """
    Phải bật cờ TRƯỚC vòng chờ, để /ready lập tức trả 503 và load balancer
    ngừng gửi request mới. Không có bước này thì vừa chờ vừa nhận thêm việc.
    """
    from app.lifecycle import Lifecycle

    lc = Lifecycle()
    assert lc.is_ready() is True
    lc.begin_shutdown()
    assert lc.is_ready() is False
    assert lc.is_shutting_down is True


@pytest.mark.asyncio
async def test_drain_cho_request_hoan_thanh():
    import asyncio
    from app.lifecycle import Lifecycle

    lc = Lifecycle()
    lc.enter_request()

    async def finish_later():
        await asyncio.sleep(0.3)
        lc.exit_request()

    asyncio.create_task(finish_later())
    await lc.drain(timeout=5)
    assert lc.in_flight == 0


@needs_redis
def test_ready_tra_503_khi_dang_tat_dan(client):
    from app.lifecycle import lifecycle

    assert client.get("/ready").status_code == 200
    lifecycle._shutting_down = True
    try:
        r = client.get("/ready")
        assert r.status_code == 503
        assert r.json()["reason"] == "shutting_down"

        # /health VẪN phải 200: trả 503 lúc này khiến orchestrator giết tiến
        # trình ngay, trước khi request đang chạy kịp hoàn thành.
        assert client.get("/health").status_code == 200
    finally:
        lifecycle._shutting_down = False


def test_signal_handler_goi_tiep_handler_cu():
    """
    Đăng ký handler mà không gọi tiếp handler cũ là VÔ HIỆU HOÁ hành vi mặc
    định — app nhận SIGTERM, ghi log, rồi chạy tiếp như chưa có gì xảy ra,
    và platform buộc phải SIGKILL sau khi hết thời gian chờ.
    """
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "app" / "lifecycle.py").read_text(encoding="utf-8")
    assert "getsignal" in src
    assert "_previous_sigterm" in src
