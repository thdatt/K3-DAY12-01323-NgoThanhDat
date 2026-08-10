"""
Chấm điểm tự động — Lab 12.

Chạy:  python grade.py

Thang điểm (100 + 10 bonus):
    CP1  12-Factor Config, Health & Logging   15
    CP2  Docker: multi-stage, bảo mật image   15
    CP3  API Security: auth, rate limit, cost 20
    CP4  Scaling & Reliability                20
    CP5  Cloud Deployment                     15
    exercises.md  10 câu phản ánh             15
    BONUS  CI/CD với GitHub Actions          +10
"""
import io
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

GREEN, RED, YELLOW, CYAN, DIM, RESET = (
    "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[2m", "\033[0m"
)


def read(rel: str) -> str:
    """Luôn đọc UTF-8. Trên Windows, open() mặc định dùng cp1252 và sẽ chết
    khi gặp tiếng Việt hoặc emoji trong chính source của lab."""
    p = ROOT / rel
    if not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


def exists(rel: str) -> bool:
    return (ROOT / rel).exists()


results = []


def check(cp: str, name: str, passed: bool, points: float, detail: str = ""):
    results.append({"cp": cp, "name": name, "passed": passed, "points": points})
    icon = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    extra = f" {DIM}— {detail}{RESET}" if detail else ""
    print(f"   [{icon}] {name} ({points}đ){extra}")


def header(title: str):
    print(f"\n{CYAN}{'─' * 66}{RESET}")
    print(f"{CYAN} {title}{RESET}")
    print(f"{CYAN}{'─' * 66}{RESET}")


# ══════════════════════════════════════════════════════════════
print(f"\n{CYAN}{'═' * 66}{RESET}")
print(f"{CYAN}  CHẤM ĐIỂM LAB 12 — Cloud Services & Deployment{RESET}")
print(f"{CYAN}  Thư mục: {ROOT.name}{RESET}")
print(f"{CYAN}{'═' * 66}{RESET}")

# ── CP1 (15đ) ─────────────────────────────────────────────────
header("CP1 — 12-Factor Config, Health & Logging (15đ)")
cfg = read("app/config.py")
logu = read("app/logging_utils.py")
main = read("app/main.py")

check("CP1", "app/config.py dùng Pydantic BaseSettings",
      "BaseSettings" in cfg, 3)
check("CP1", "agent_api_key KHÔNG có giá trị mặc định (fail-fast)",
      bool(re.search(r"agent_api_key:\s*str\s*(#.*)?$", cfg, re.M)), 3,
      "app phải chết ngay nếu thiếu key")
check("CP1", "app/logging_utils.py log ra JSON",
      "json.dumps" in logu and "timestamp" in logu, 3)
check("CP1", "Log có trường event + level",
      '"event"' in logu and '"level"' in logu, 2)
check("CP1", "Có endpoint /health",
      '"/health"' in main, 2)
check("CP1", "Có endpoint /ready kiểm tra Redis",
      '"/ready"' in main and "ping" in main, 2)

# ── CP2 (15đ) ─────────────────────────────────────────────────
header("CP2 — Docker: Multi-stage & Bảo mật (15đ)")
dockerfile = read("Dockerfile")
compose = read("docker-compose.yml")
dockerignore = read(".dockerignore")

check("CP2", "Dockerfile multi-stage (>= 2 FROM)",
      len(re.findall(r"^FROM ", dockerfile, re.M)) >= 2, 3)
check("CP2", "Dùng base image slim/alpine",
      "slim" in dockerfile or "alpine" in dockerfile, 2)
check("CP2", "Chạy bằng non-root user",
      bool(re.search(r"^USER \w+", dockerfile, re.M))
      and not re.search(r"^USER root", dockerfile, re.M), 3)
check("CP2", "COPY requirements.txt trước khi COPY code (layer cache)",
      ("COPY requirements.txt" in dockerfile and "COPY app/" in dockerfile
       and dockerfile.index("COPY requirements.txt") < dockerfile.index("COPY app/")), 2)
check("CP2", "Có HEALTHCHECK",
      "HEALTHCHECK" in dockerfile, 2)
check("CP2", ".dockerignore có .env, __pycache__, .git",
      all(k in dockerignore for k in (".env", "__pycache__", ".git")), 1)
check("CP2", "docker-compose có đủ redis + agent + nginx",
      all(f"{s}:" in compose for s in ("redis", "agent", "nginx")), 1)
check("CP2", "agent dùng expose (không publish port → scale được)",
      "expose:" in compose, 1)

# ── CP3 (20đ) ─────────────────────────────────────────────────
header("CP3 — API Security (20đ)")
auth = read("app/auth.py")
rl = read("app/rate_limiter.py")
cg = read("app/cost_guard.py")

check("CP3", "app/auth.py kiểm tra header X-API-Key",
      "X-API-Key" in auth, 3)
check("CP3", "Sai/thiếu key trả 401",
      "401" in auth, 3)
check("CP3", "So sánh key chống timing attack (compare_digest)",
      "compare_digest" in auth, 2)
check("CP3", "Rate limit dùng Redis Sorted Set",
      "zremrangebyscore" in rl and "zcard" in rl and "zadd" in rl, 4)
check("CP3", "Member duy nhất bằng uuid (tránh ghi đè)",
      "uuid" in rl, 2)
check("CP3", "Vượt quota trả 429",
      "429" in rl, 2)
check("CP3", "Cost guard key theo tháng cost:<user>:<YYYY-MM>",
      "%Y-%m" in cg and "cost:" in cg, 2)
check("CP3", "Vượt ngân sách trả 402",
      "402" in cg, 2)

# ── CP4 (20đ) ─────────────────────────────────────────────────
header("CP4 — Scaling & Reliability (20đ)")
store = read("app/store.py")
life = read("app/lifecycle.py")

check("CP4", "app/store.py lưu lịch sử vào Redis List",
      "rpush" in store and "lrange" in store, 4)
check("CP4", "Có append_message() và get_history()",
      "def append_message" in store and "def get_history" in store, 3)
check("CP4", "app/lifecycle.py xử lý SIGTERM",
      "SIGTERM" in life, 3)
check("CP4", "Gọi tiếp handler cũ (không nuốt tín hiệu)",
      "getsignal" in life, 3)
check("CP4", "Đợi request đang chạy hoàn thành (drain)",
      "drain" in life and "in_flight" in life, 3)
check("CP4", "/ready trả 503 khi đang tắt dần",
      "503" in main and "shutting_down" in main, 2)
check("CP4", "/ask trả history_length",
      "history_length" in main, 2)

# ── CP5 (15đ) ─────────────────────────────────────────────────
header("CP5 — Cloud Deployment (15đ)")
deploy_md = read("DEPLOYMENT.md")
railway = read("railway.toml")
render = read("render.yaml")

has_url = bool(re.search(r"https://[\w.-]+\.(up\.railway\.app|onrender\.com)", deploy_md))
local_fallback = "LOCAL_FALLBACK=true" in read(".env")

check("CP5", "Có railway.toml hoặc render.yaml",
      bool(railway or render), 2)
check("CP5", "startCommand bọc sh -c để expand $PORT",
      ("sh" in railway and "-c" in railway) if railway else True, 3,
      "Railway chạy exec, không qua shell")
check("CP5", "DEPLOYMENT.md có Public URL thật",
      has_url, 4,
      "hoặc LOCAL_FALLBACK (tối đa 9/15)" if not has_url else "")
check("CP5", "DEPLOYMENT.md có đủ 4 bằng chứng (/health /ready 401 200)",
      all(k in deploy_md for k in ("/health", "/ready", "401", "200")), 3)

shots = list((ROOT / "screenshots").glob("*.png")) if exists("screenshots") else []
check("CP5", "screenshots/ có ảnh dashboard và ảnh /health",
      len(shots) >= 2, 3, f"tìm thấy {len(shots)} ảnh")

# ── exercises.md (15đ) ────────────────────────────────────────
header("exercises.md — 10 câu phản ánh (15đ)")
ex = read("exercises.md")
questions = re.findall(r"^##\s*C(?:â|a)u\s*\d+", ex, re.M)
n = len(questions)
check("exercises", f"Đủ 10 câu (tìm thấy {n})", n >= 10, 10)
check("exercises", "Câu trả lời có độ sâu (>= 3000 ký tự)",
      len(ex) >= 3000, 3, f"{len(ex)} ký tự")
check("exercises", "Có dẫn chứng số liệu thực tế",
      bool(re.search(r"\d+\s*(MB|GB|giây|ms|đ|%)", ex)), 2)

# ── BONUS (+10) ───────────────────────────────────────────────
header("BONUS — CI/CD với GitHub Actions (+10đ)")
workflows = list((ROOT / ".github" / "workflows").glob("*.yml")) \
    if exists(".github/workflows") else []
bonus_ok = len(workflows) > 0
check("BONUS", "Có .github/workflows/*.yml", bonus_ok, 10,
      "chưa làm — không ảnh hưởng 100đ chính" if not bonus_ok else "")

# ── Bảo mật (không tính điểm, nhưng phải đạt) ─────────────────
header("Kiểm tra bảo mật (bắt buộc)")
try:
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT,
                             capture_output=True, text=True, timeout=30).stdout
    env_tracked = [l for l in tracked.splitlines()
                   if l == ".env" or l.endswith("/.env")]
except Exception:
    env_tracked = []

if env_tracked:
    print(f"   [{RED}NGUY HIỂM{RESET}] .env đang bị Git theo dõi: {env_tracked}")
else:
    print(f"   [{GREEN}PASS{RESET}] .env không nằm trong repo")

name_ok = bool(re.match(r"^K\d+-DAY12-[\w]+-[\w]+$", ROOT.name))
icon = f"{GREEN}PASS{RESET}" if name_ok else f"{YELLOW}WARN{RESET}"
print(f"   [{icon}] Tên thư mục đúng format KX-DAY12-[MSSV]-[HoVaTen]")

# ══════════════════════════════════════════════════════════════
print(f"\n{CYAN}{'═' * 66}{RESET}")

core = [r for r in results if r["cp"] != "BONUS"]
earned = sum(r["points"] for r in core if r["passed"])
total = sum(r["points"] for r in core)
bonus = sum(r["points"] for r in results if r["cp"] == "BONUS" and r["passed"])

by_cp = {}
for r in core:
    e, t = by_cp.get(r["cp"], (0, 0))
    by_cp[r["cp"]] = (e + (r["points"] if r["passed"] else 0), t + r["points"])

print(f"{CYAN}  KẾT QUẢ{RESET}\n")
for cp in ("CP1", "CP2", "CP3", "CP4", "CP5", "exercises"):
    if cp in by_cp:
        e, t = by_cp[cp]
        bar = f"{GREEN}{'█' * int(e / t * 20)}{RESET}{DIM}{'░' * (20 - int(e / t * 20))}{RESET}"
        print(f"   {cp:<12} {bar}  {e:>5.1f} / {t}")

print(f"\n   {'TỔNG':<12} {' ' * 20}  {earned:>5.1f} / {total}")
if bonus:
    print(f"   {'BONUS':<12} {' ' * 20}  {bonus:>5.1f} / 10")
    print(f"   {'CỘNG BONUS':<12} {' ' * 20}  {earned + bonus:>5.1f}")

failed = [r for r in core if not r["passed"]]
if failed:
    print(f"\n{YELLOW}  Còn thiếu:{RESET}")
    for r in failed:
        print(f"   • [{r['cp']}] {r['name']} ({r['points']}đ)")

print()
if earned >= 75:
    print(f"   {GREEN}ĐẠT MỤC TIÊU — {earned:.1f}/100 (yêu cầu >= 75){RESET}")
else:
    print(f"   {RED}CHƯA ĐẠT — {earned:.1f}/100 (cần >= 75){RESET}")
print(f"{CYAN}{'═' * 66}{RESET}\n")

sys.exit(0 if earned >= 75 else 1)
