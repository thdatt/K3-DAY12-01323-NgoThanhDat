"""CP2 — Docker: multi-stage build & bảo mật image."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
DOCKERIGNORE = (ROOT / ".dockerignore").read_text(encoding="utf-8")


def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True,
                              timeout=15).returncode == 0
    except Exception:
        return False


needs_docker = pytest.mark.skipif(
    not docker_available(),
    reason="Cần Docker daemon đang chạy",
)


# ── 2.1 Multi-stage build ─────────────────────────────────────
def test_dockerfile_la_multi_stage():
    """Phải có ít nhất 2 lệnh FROM — stage builder và stage runtime."""
    assert len(re.findall(r"^FROM ", DOCKERFILE, re.M)) >= 2
    assert re.search(r"FROM .+ AS builder", DOCKERFILE)
    assert "COPY --from=builder" in DOCKERFILE


def test_dung_base_image_slim():
    assert "slim" in DOCKERFILE or "alpine" in DOCKERFILE


def test_copy_requirements_TRUOC_khi_copy_code():
    """
    Thứ tự này quyết định Docker layer cache.

    Nếu COPY code lên trước pip install, sửa 1 dòng code cũng khiến pip
    install chạy lại từ đầu — build từ vài giây thành vài phút.
    """
    i_req = DOCKERFILE.index("COPY requirements.txt")
    i_pip = DOCKERFILE.index("pip install")
    i_app = DOCKERFILE.index("COPY app/")
    assert i_req < i_pip < i_app


# ── 2.2 Bảo mật: non-root ─────────────────────────────────────
def test_chay_bang_user_thuong_khong_phai_root():
    """
    Container mặc định chạy root. Có lỗ hổng trong code → kẻ tấn công có
    quyền root trong container → có thể leo thang ra máy host.
    """
    assert re.search(r"(adduser|useradd)", DOCKERFILE)
    assert re.search(r"^USER \w+", DOCKERFILE, re.M)
    assert not re.search(r"^USER root", DOCKERFILE, re.M)


def test_co_healthcheck():
    assert "HEALTHCHECK" in DOCKERFILE


def test_cmd_dung_shell_form_de_expand_PORT():
    """
    Cloud platform cấp cổng ngẫu nhiên qua biến PORT.

    Viết exec form ["uvicorn", "--port", "$PORT"] sẽ truyền nguyên văn chuỗi
    "$PORT" cho uvicorn → lỗi 'not a valid integer'.
    """
    cmd_line = [l for l in DOCKERFILE.splitlines() if l.startswith("CMD")][-1]
    assert "sh" in cmd_line and "-c" in cmd_line
    assert "PORT" in cmd_line


# ── 2.3 .dockerignore ─────────────────────────────────────────
@pytest.mark.parametrize("entry", [".env", "__pycache__", ".git", "screenshots"])
def test_dockerignore_co_muc_can_thiet(entry):
    assert entry in DOCKERIGNORE


# ── 2.4 docker-compose.yml ────────────────────────────────────
def test_compose_co_du_3_service():
    for svc in ("redis:", "agent:", "nginx:"):
        assert svc in COMPOSE


def test_agent_KHONG_publish_port_ra_host():
    """
    Agent phải dùng `expose`, không phải `ports`.

    Publish 8000:8000 thì `--scale agent=3` sẽ lỗi vì 3 container tranh nhau
    cùng một cổng. Cổng 8000 trên host chỉ map qua Nginx (8000:80).
    """
    agent_block = COMPOSE[COMPOSE.index("agent:"):COMPOSE.index("nginx:")]
    assert "expose:" in agent_block
    assert not re.search(r'^\s+ports:', agent_block, re.M)


def test_agent_cho_redis_healthy_moi_khoi_dong():
    """
    `depends_on: [redis]` suông chỉ đợi container ĐƯỢC TẠO, không đợi Redis
    SẴN SÀNG nhận lệnh — agent sẽ crash vì kết nối lúc Redis còn đang boot.
    """
    assert "condition: service_healthy" in COMPOSE


def test_compose_bat_buoc_co_AGENT_API_KEY():
    """Cú pháp ${VAR:?msg} khiến Compose dừng ngay với thông báo rõ ràng."""
    assert "AGENT_API_KEY:?" in COMPOSE or "AGENT_API_KEY:?" in COMPOSE.replace("${", "")


def test_nginx_map_cong_8000():
    assert '"8000:80"' in COMPOSE


# ── 2.5 Kiểm tra image thật (cần Docker) ──────────────────────
@needs_docker
def test_image_duoi_500MB():
    out = subprocess.run(
        ["docker", "images", "day12-agent:prod", "--format", "{{.Size}}"],
        capture_output=True, text=True, timeout=30,
    ).stdout.strip()

    if not out:
        pytest.skip("Chưa build image: docker build -t day12-agent:prod .")

    value = float(re.sub(r"[^0-9.]", "", out))
    mb = value * 1024 if "GB" in out else value
    assert mb <= 500, f"Image {out} vượt 500MB"
