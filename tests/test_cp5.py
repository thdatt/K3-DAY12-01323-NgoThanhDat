"""CP5 — Cloud Deployment: cấu hình và bằng chứng nộp bài."""
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def read(name: str) -> str:
    p = ROOT / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


# ── 5.1 File cấu hình nền tảng ────────────────────────────────
def test_co_file_cau_hinh_cloud():
    assert (ROOT / "railway.toml").exists() or (ROOT / "render.yaml").exists()


def test_railway_boc_sh_c_de_expand_PORT():
    """
    Railway chạy startCommand ở dạng exec (không qua shell), nên "$PORT"
    được truyền nguyên văn cho uvicorn:
        Error: Invalid value for '--port': '$PORT' is not a valid integer.
    """
    toml = read("railway.toml")
    if not toml:
        pytest.skip("Không dùng Railway")

    start = [l for l in toml.splitlines() if l.strip().startswith("startCommand")]
    assert start, "railway.toml thiếu startCommand"
    assert "sh" in start[0] and "-c" in start[0]


def test_railway_co_healthcheck():
    toml = read("railway.toml")
    if not toml:
        pytest.skip("Không dùng Railway")
    assert "healthcheckPath" in toml


def test_KHONG_hardcode_PORT_trong_cau_hinh():
    """Cloud cấp cổng ngẫu nhiên — hardcode 8000 sẽ khiến health check fail."""
    for name in ("railway.toml", "render.yaml"):
        content = read(name)
        if content:
            assert not re.search(r"^\s*PORT\s*[:=]\s*8000", content, re.M)


# ── 5.2 Bằng chứng nộp bài ────────────────────────────────────
def test_deployment_md_ton_tai_va_co_url():
    doc = read("DEPLOYMENT.md")
    assert doc, "Thiếu DEPLOYMENT.md"

    has_url = re.search(r"https://[\w.-]+\.(up\.railway\.app|onrender\.com)", doc)
    has_fallback = "LOCAL_FALLBACK" in doc
    assert has_url or has_fallback, "DEPLOYMENT.md cần URL thật hoặc LOCAL_FALLBACK"


def test_deployment_md_co_du_4_bang_chung():
    doc = read("DEPLOYMENT.md")
    for evidence in ("/health", "/ready", "401", "200"):
        assert evidence in doc


def test_co_thu_muc_screenshots_va_co_anh():
    d = ROOT / "screenshots"
    assert d.is_dir(), "Thiếu thư mục screenshots/"
    images = list(d.glob("*.png")) + list(d.glob("*.jpg"))
    assert len(images) >= 2, "Cần ít nhất ảnh dashboard và ảnh gọi /health"


def test_exercises_md_du_10_cau():
    doc = read("exercises.md")
    assert doc, "Thiếu exercises.md"
    assert len(re.findall(r"^##\s*C(â|a)u\s*\d+", doc, re.M)) >= 10


# ── 5.3 Bảo mật khi nộp ───────────────────────────────────────
def test_env_KHONG_bi_commit():
    import subprocess
    out = subprocess.run(["git", "ls-files"], cwd=ROOT,
                         capture_output=True, text=True, timeout=30).stdout
    tracked = [l for l in out.splitlines() if l == ".env" or l.endswith("/.env")]
    assert not tracked, f"NGUY HIỂM: .env đang bị theo dõi! {tracked}"


def test_gitignore_chan_env():
    gi = read(".gitignore")
    assert ".env" in gi


def test_khong_hardcode_secret_trong_code():
    for name in ("app/main.py", "app/config.py", "app/auth.py"):
        src = read(name)
        for bad in ("sk-", "password123", "hardcoded"):
            assert bad not in src, f"{name} có vẻ chứa secret hardcode: {bad}"


def test_ten_thu_muc_dung_format():
    """Format bắt buộc: KX-DAY12-[MSSV]-[HoVaTen]"""
    assert re.match(r"^K\d+-DAY12-[\w]+-[\w]+$", ROOT.name), \
        f"Tên thư mục '{ROOT.name}' không khớp KX-DAY12-[MSSV]-[HoVaTen]"
