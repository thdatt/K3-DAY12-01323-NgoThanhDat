"""CP1 — 12-Factor Config, Health & Logging."""
import json
import logging
import os

import pytest

from conftest import needs_redis


# ── 1.1 Settings 12-Factor ────────────────────────────────────
def test_settings_doc_tu_env():
    """Config phải đọc từ biến môi trường, không hardcode."""
    from app.config import settings
    assert settings.agent_api_key == os.environ["AGENT_API_KEY"]
    assert settings.rate_limit_per_minute == 10
    assert settings.monthly_budget_usd == 10.0


def test_settings_co_gia_tri_mac_dinh_hop_ly():
    from app.config import Settings
    fields = Settings.model_fields
    assert fields["port"].default == 8000
    assert fields["rate_limit_per_minute"].default == 10
    assert fields["monthly_budget_usd"].default == 10.0


def test_agent_api_key_KHONG_co_gia_tri_mac_dinh():
    """
    Fail-fast: agent_api_key phải là trường bắt buộc.

    Nếu có giá trị mặc định kiểu "changeme", app sẽ khởi động bình thường
    nhưng chạy với key giả — ai cũng gọi được API.
    """
    from app.config import Settings
    assert Settings.model_fields["agent_api_key"].is_required()


@pytest.mark.parametrize("bad_key", ["", "changeme", "CHANGEME", "your-api-key", "todo"])
def test_placeholder_key_bi_chan(bad_key, monkeypatch):
    """Key rỗng hoặc còn là placeholder → phải dừng app ngay."""
    from app.config import _validate, Settings
    monkeypatch.setenv("AGENT_API_KEY", bad_key)
    with pytest.raises((ValueError, Exception)):
        _validate(Settings())


# ── 1.2 Structured Logging ────────────────────────────────────
def test_log_ra_dung_dinh_dang_json():
    from app.logging_utils import JsonFormatter

    record = logging.LogRecord(
        name="agent", level=logging.INFO, pathname=__file__, lineno=1,
        msg="ask_completed", args=(), exc_info=None,
    )
    record.user_id = "sv01"
    record.latency_ms = 812

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["event"] == "ask_completed"
    assert payload["user_id"] == "sv01"
    assert payload["latency_ms"] == 812
    assert payload["timestamp"].endswith("Z")   # UTC


def test_setup_logging_ep_ghi_de_cau_hinh_cu():
    """
    force=True phải ép ghi đè handler đã tồn tại.

    Thiếu nó, nếu thư viện nào đó lỡ gọi logging.warning() trước thì root
    logger đã có handler và basicConfig() sẽ im lặng không làm gì — toàn bộ
    log JSON biến mất.
    """
    from app.logging_utils import JsonFormatter, setup_logging

    logging.basicConfig(level=logging.WARNING, force=True)   # cấu hình "rác"
    setup_logging("INFO")

    root = logging.getLogger()
    assert root.level == logging.INFO
    assert any(isinstance(h.formatter, JsonFormatter) for h in root.handlers)


# ── 1.3 Health & Readiness ────────────────────────────────────
@needs_redis
def test_health_tra_ve_200(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@needs_redis
def test_health_KHONG_goi_redis(client, monkeypatch):
    """
    /health là liveness — không được phụ thuộc Redis.

    Nếu có, Redis trục trặc 5 giây sẽ khiến platform restart đồng loạt mọi
    container, biến sự cố nhỏ ở tầng cache thành sập cả hệ thống.
    """
    import app.main as main

    def no_redis(*a, **kw):
        raise ConnectionError("redis down")

    monkeypatch.setattr(main.redis_client, "ping", no_redis)
    assert client.get("/health").status_code == 200


@needs_redis
def test_ready_tra_ve_200_khi_redis_song(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["ready"] is True


@needs_redis
def test_ready_tra_ve_503_khi_mat_redis(client, monkeypatch):
    """/ready là readiness — phải 503 khi dependency hỏng."""
    import app.main as main

    def no_redis(*a, **kw):
        raise ConnectionError("redis down")

    monkeypatch.setattr(main.redis_client, "ping", no_redis)
    r = client.get("/ready")
    assert r.status_code == 503
    assert r.json()["ready"] is False
