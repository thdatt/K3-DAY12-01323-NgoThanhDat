# Day 12 Lab - Mission Answers

> **Student Name:** Ngô Thành Đạt
> **Student ID:** 2A202601323
> **Date:** 10/08/2026
> **Môi trường test:** Windows 11, Python 3.12.10, venv cục bộ

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

Anti-patterns tìm được trong `01-localhost-vs-production/develop/app.py`.

Yêu cầu tối thiểu 5 vấn đề. Dưới đây là **11 vấn đề** tìm được, kèm số dòng.

| # | Dòng | Anti-pattern | Hậu quả trong production | Vi phạm nguyên tắc |
|---|------|--------------|--------------------------|--------------------|
| 1 | 17 | Hardcode API key: `OPENAI_API_KEY = "sk-hardcoded-..."` | Push lên GitHub public → bot scan repo trong vài giây, key bị lộ và bị dùng chùa | 12-Factor III (Config) |
| 2 | 18 | Hardcode connection string kèm mật khẩu: `postgresql://admin:password123@...` | Lộ credential DB; muốn đổi DB phải sửa code + rebuild | 12-Factor III |
| 3 | 21–22 | Config nằm trong code (`DEBUG = True`, `MAX_TOKENS = 500`) | Không đổi được giữa dev/staging/prod nếu không sửa code | 12-Factor III |
| 4 | 33, 38 | Dùng `print()` thay vì `logging` | Không có level/timestamp, không đẩy được vào Datadog/Loki, không lọc được theo severity | 12-Factor XI (Logs) |
| 5 | 34 | **Log chính secret ra stdout**: `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` | Secret nằm vĩnh viễn trong log của cloud platform — ai đọc được log là đọc được key | Security |
| 6 | 42–43 | Không có endpoint `/health` và `/ready` | Platform không biết container đã chết để restart; load balancer vẫn route traffic vào instance hỏng. **Đã test: cả 2 đều trả 404** | 12-Factor IX (Disposability) |
| 7 | 51 | `host="localhost"` | Trong container chỉ bind vào loopback → `docker run -p 8000:8000` map vào nhưng không ai gọi được từ ngoài. Phải là `0.0.0.0` | Container-readiness |
| 8 | 52 | `port=8000` cứng | Railway / Render / Cloud Run **inject biến `PORT`** và bắt app phải listen đúng port đó. Bỏ qua `PORT` → healthcheck fail → deploy fail | 12-Factor VII (Port binding) |
| 9 | 53 | `reload=True` | File-watcher của dev chạy trong production: tốn RAM/CPU, restart bất chợt khi filesystem thay đổi | Dev/prod parity |
| 10 | — | Không có SIGTERM handler / graceful shutdown | Khi platform deploy bản mới, nó gửi SIGTERM → process chết ngay → request đang xử lý dở bị đứt, user nhận 502 | 12-Factor IX |
| 11 | 31 | `def ask_agent(question: str)` — tham số kiểu `str` trần | FastAPI hiểu đây là **query parameter**, KHÔNG phải JSON body. Đúng ra phải dùng Pydantic `BaseModel` | API design |

#### Bằng chứng cho vấn đề #11

Chạy đúng lệnh curl mà `CODE_LAB.md` hướng dẫn:

```bash
curl http://localhost:8000/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
```

Kết quả **HTTP 422**, không phải 200:

```json
{"detail":[{"type":"missing","loc":["query","question"],"msg":"Field required","input":null}]}
```

Chỉ chạy được khi truyền qua query string:

```bash
curl -X POST "http://localhost:8000/ask?question=What%20is%20Docker"
# 200 OK
# {"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

Cách sửa đúng:

```python
from pydantic import BaseModel

class AskRequest(BaseModel):
    question: str

@app.post("/ask")
def ask_agent(req: AskRequest):
    ...
```

#### Bằng chứng cho vấn đề #6

```
GET /health  -> HTTP 404
GET /ready   -> HTTP 404
```

---

### Exercise 1.2: Run the develop version

```bash
python -m venv .venv
.\.venv\Scripts\activate                    # Windows
pip install -r 01-localhost-vs-production/develop/requirements.txt
cd 01-localhost-vs-production/develop
python app.py
```

Kết quả test:

| Endpoint | Method | Kết quả |
|----------|--------|---------|
| `/` | GET | 200 — `{"message":"Hello! Agent is running on my machine :)"}` |
| `/ask?question=...` | POST | 200 — trả lời từ mock LLM |
| `/ask` + JSON body | POST | **422** — sai thiết kế API (xem #11) |
| `/health` | GET | **404** — không tồn tại |
| `/ready` | GET | **404** — không tồn tại |

**Nhận xét:** app *có chạy*, nhưng chỉ chạy được trên máy mình. Đưa lên cloud là fail ngay ở bước healthcheck vì thiếu `/health` và không đọc biến `PORT`.

---

### Exercise 1.3: Comparison table

```bash
cd 01-localhost-vs-production/production
cp .env.example .env
pip install -r requirements.txt
python app.py
```

| Feature | Develop (❌) | Production (✅) | Tại sao quan trọng? |
|---------|-------------|----------------|---------------------|
| **Config** | Hardcode trong `app.py` | `config.py` đọc `os.getenv()`, có default an toàn | Cùng 1 image chạy được ở mọi môi trường — chỉ đổi env var, không rebuild |
| **Secrets** | `OPENAI_API_KEY = "sk-..."` trong code | Đọc từ env, `.env` bị `.gitignore` chặn | Code lên Git công khai mà secret không lộ; rotate key không cần đụng code |
| **Validation config** | Không có | `Settings.validate()` — raise nếu thiếu `AGENT_API_KEY` khi `ENVIRONMENT=production` | **Fail fast**: chết lúc khởi động (dễ thấy) thay vì chết lúc user gọi API (khó debug) |
| **Host binding** | `localhost` | `0.0.0.0` (từ `HOST`) | `localhost` trong container = không ai gọi vào được từ ngoài |
| **Port** | Cứng `8000` | `int(os.getenv("PORT", "8000"))` | Railway/Render/Cloud Run tự inject `PORT`, không nghe đúng port thì deploy fail |
| **Health check** | Không có (404) | `GET /health` → uptime, version, env | Liveness probe: platform tự restart container chết |
| **Readiness** | Không có (404) | `GET /ready` → 503 khi chưa sẵn sàng | Load balancer không đẩy traffic vào instance đang khởi động |
| **Metrics** | Không có | `GET /metrics` | Prometheus scrape được → dựng dashboard/alert |
| **Logging** | `print()`, log cả secret | `logging` + JSON format, chỉ log `question_length` và `client_ip` | Log parse được bằng máy, và **không rò rỉ secret** |
| **Shutdown** | Chết đột ngột | `lifespan` + handler `SIGTERM` | Request đang chạy được hoàn thành → zero-downtime deploy |
| **Lifecycle** | Không có | `@asynccontextmanager lifespan` với cờ `is_ready` | Tách bạch startup (load model, mở connection) và shutdown (đóng connection) |
| **CORS** | Không có | `CORSMiddleware` với `ALLOWED_ORIGINS` | Kiểm soát domain nào được gọi API từ browser |
| **Reload** | `reload=True` luôn bật | `reload=settings.debug` | Production không chạy file-watcher tốn tài nguyên |
| **API contract** | Query param ngầm định | Đọc JSON body + raise 422 kèm message rõ ràng | Client biết chính xác mình sai chỗ nào |

Kết quả test bản production — **tất cả đều pass**:

```
GET  /         -> 200  {"app":"AI Agent","version":"1.0.0","environment":"development","status":"running"}
GET  /health   -> 200  {"status":"ok","uptime_seconds":8.2,"version":"1.0.0",...}
GET  /ready    -> 200  {"ready":true}
GET  /metrics  -> 200  {"uptime_seconds":8.7,"environment":"development","version":"1.0.0"}
POST /ask      -> 200  {"question":"Hello deploy","answer":"Deployment là quá trình...","model":"gpt-4o-mini"}
POST /ask (body rỗng) -> 422  {"detail":"question field is required"}
```

---

### Bonus — 2 bug tìm được trong chính bản "production" mẫu (đã sửa)

Bản production tốt hơn hẳn bản develop, nhưng tự test kỹ thì phát hiện 2 lỗi thật. **Cả 2 đã được sửa và verify lại.**

> ⚠️ Lưu ý: chỉ sửa trong `production/`. File `develop/app.py` **cố tình giữ nguyên toàn bộ lỗi**, vì đó chính là đề bài của Exercise 1.1.

#### Bug A — File `.env` không hề được đọc

`requirements.txt` có khai báo `python-dotenv==1.0.1`, nhưng **không file nào trong repo gọi `load_dotenv()`**:

```bash
grep -rn "load_dotenv" . --include=*.py
# (không có kết quả)
```

Thí nghiệm chứng minh — sửa `.env` thành `APP_NAME=Day12-Agent-NgoThanhDat` rồi khởi động lại:

```json
GET /  ->  {"app":"AI Agent", ...}      // vẫn là giá trị default, .env bị bỏ qua
```

Cùng biến đó nhưng set qua env var thật của OS:

```powershell
$env:APP_NAME="Day12-Agent-NgoThanhDat"; $env:ENVIRONMENT="staging"; python app.py
```
```json
GET /  ->  {"app":"Day12-Agent-NgoThanhDat","environment":"staging", ...}   // OK
```

→ `config.py` chạy đúng, chỉ là bước nạp `.env` bị thiếu. Hướng dẫn `cp .env.example .env` trong `CODE_LAB.md` do đó không có tác dụng gì khi chạy local.

**✅ Đã sửa** — thêm vào đầu `config.py`, **trước** khi khai báo class `Settings`:

```python
from dotenv import load_dotenv
load_dotenv()          # nạp .env vào os.environ; env var thật của OS vẫn được ưu tiên
```

`load_dotenv()` mặc định `override=False`, nên biến môi trường thật do cloud platform inject (ví dụ `PORT` của Railway) vẫn thắng file `.env`. Đúng thứ tự ưu tiên mà 12-Factor mong muốn.

Kết quả sau khi sửa — `.env` đã có tác dụng:

```json
GET /  ->  {"app":"Day12-Agent-NgoThanhDat","version":"1.0.0","environment":"development","status":"running"}
```

#### Bug B — Structured JSON logging không bao giờ chạy

`app.py` cấu hình log JSON ở dòng 28–31, nhưng thực tế không có dòng JSON nào xuất hiện. Log thực nhận được:

```
WARNING:root:OPENAI_API_KEY not set — using mock LLM     <- format mặc định, không phải JSON
INFO:     127.0.0.1 - "POST /ask HTTP/1.1" 200 OK        <- log của uvicorn
```

Toàn bộ `logger.info(json.dumps({"event": "startup", ...}))` và `{"event": "agent_request", ...}` bị nuốt mất.

**Nguyên nhân gốc** (đã kiểm chứng bằng script):

1. `app.py` dòng 24 `from config import settings` chạy **trước** `logging.basicConfig()` ở dòng 28.
2. Lúc import, `config.py` gọi `logging.warning(...)` trong `validate()`. `logging.warning()` ở module level sẽ **tự động gọi `basicConfig()` với default** → root logger được gắn handler, level = `WARNING`.
3. Đến dòng 28, `logging.basicConfig(level=INFO, format='{"time":...}')` trở thành **no-op**, vì `basicConfig()` không làm gì nếu root logger đã có handler.
4. Root logger giữ nguyên level `WARNING` → mọi `logger.info(...)` bị lọc bỏ, và format JSON không bao giờ được áp dụng.

```
root handlers trước khi import config : []
root handlers sau khi import config   : [<StreamHandler <stderr>>]
root level sau khi gọi basicConfig    : WARNING     <- basicConfig bị bỏ qua
formatter đang dùng                   : %(levelname)s:%(name)s:%(message)s
```

**✅ Đã sửa** bằng 2 thay đổi bổ trợ nhau:

*1. `app.py` — thêm `force=True` (Python 3.8+) để ép ghi đè cấu hình cũ:*

```python
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
    force=True,      # <- ghi đè handler mà config.py đã vô tình tạo ra
)
```

*2. `config.py` — xử lý tận gốc: không log lúc import nữa, chỉ gom cảnh báo lại:*

```python
startup_warnings: list = field(default_factory=list)

def validate(self):
    if not self.openai_api_key:
        self.startup_warnings.append("OPENAI_API_KEY not set — using mock LLM")
    if not self.api_key and self.environment == "production":
        raise ValueError("AGENT_API_KEY must be set in production!")   # lỗi nặng thì vẫn fail fast
    return self
```

*rồi `app.py` log chúng ra SAU khi logging đã cấu hình xong:*

```python
for _warning in settings.startup_warnings:
    logger.warning(_warning)
```

Chỉ dùng `force=True` thì dòng warning đầu tiên vẫn lọt ra ở format cũ (`WARNING:root:...`), vì nó đã bị in ra từ lúc import. Phải sửa cả `config.py` mới sạch hoàn toàn.

Log sau khi sửa — **mọi dòng của app đều là JSON**:

```json
{"time":"2026-08-10 09:56:50,853","level":"WARNING","msg":"OPENAI_API_KEY not set — using mock LLM"}
{"time":"2026-08-10 09:56:50,854","level":"INFO","msg":"Starting Day12-Agent-NgoThanhDat on 0.0.0.0:8000"}
{"time":"2026-08-10 09:56:50,888","level":"INFO","msg":"{"event": "startup", "app": "Day12-Agent-NgoThanhDat", ...}"}
{"time":"2026-08-10 09:56:50,988","level":"INFO","msg":"Agent is ready to serve requests"}
{"time":"2026-08-10 09:57:02,048","level":"INFO","msg":"{"event": "agent_request", "question_length": 17, "client_ip": "127.0.0.1"}"}
{"time":"2026-08-10 09:57:02,163","level":"INFO","msg":"{"event": "agent_response", "response_length": 96}"}
```

**Bài học rút ra:** đừng gọi `logging.warning()` ở module level trong file config — hãy để việc cấu hình logging cho entrypoint của app.

*(Các dòng `INFO: 127.0.0.1 - "GET /health HTTP/1.1" 200 OK` vẫn ở format thường vì đó là access log của **uvicorn**, dùng logger riêng. Muốn JSON hoá cả phần này phải truyền `log_config` tuỳ chỉnh vào `uvicorn.run()` — sẽ làm ở Part 6.)*

#### Regression test sau khi sửa — tất cả pass

```
GET  /         -> 200   {"app":"Day12-Agent-NgoThanhDat",...}   <- .env đã có tác dụng
GET  /health   -> 200   {"status":"ok","uptime_seconds":10.4,...}
GET  /ready    -> 200   {"ready":true}
GET  /metrics  -> 200   {"uptime_seconds":10.9,...}
POST /ask      -> 200   {"question":"Hello sau khi fix","answer":"...","model":"gpt-4o-mini"}
POST /ask {}   -> 422   {"detail":"question field is required"}
```

---

### ✅ Checkpoint 1

- [x] Hiểu tại sao hardcode secrets là nguy hiểm
- [x] Biết cách dùng environment variables
- [x] Hiểu vai trò của health check endpoint
- [x] Biết graceful shutdown là gì

---

## Part 2: Docker

> Môi trường: Docker 29.6.2, Docker Compose v5.3.1, backend WSL2 (OSType = linux).

### Exercise 2.1: Dockerfile questions

File phân tích: `02-docker/develop/Dockerfile`

**1. Base image là gì?**

`FROM python:3.11` — bản Python đầy đủ, nền Debian bookworm, khoảng **1 GB**.

Nó chứa cả bộ công cụ build: `gcc`, `make`, `git`, header của Python… Rất tiện khi cài package phải compile, nhưng đưa nguyên si lên production là lãng phí và **tăng bề mặt tấn công** — mỗi binary thừa trong image là một CVE tiềm năng.

Các lựa chọn thay thế:

| Tag | Size | Đánh đổi |
|---|---|---|
| `python:3.11` | ~1 GB | Đầy đủ nhất, build gì cũng được |
| `python:3.11-slim` | ~150 MB | Bỏ build tools — bản `production/` dùng cái này |
| `python:3.11-alpine` | ~50 MB | Nhỏ nhất nhưng dùng musl libc, hay lỗi với package có C extension |

**2. Working directory là gì?**

`WORKDIR /app` (dòng 11).

`WORKDIR` vừa `cd` vừa `mkdir -p` nếu thư mục chưa tồn tại. Mọi lệnh `COPY`, `RUN`, `CMD` phía sau đều lấy `/app` làm gốc. Nhờ vậy `COPY ... .` ở dòng 14 nghĩa là copy vào `/app/`.

**3. Tại sao COPY requirements.txt TRƯỚC rồi mới COPY code?**

Đây là kỹ thuật tận dụng **Docker layer cache** — mỗi lệnh trong Dockerfile tạo ra một layer, Docker chỉ build lại layer khi nội dung đầu vào của nó đổi, và **một layer đổi thì mọi layer sau nó đều mất cache**.

```dockerfile
COPY requirements.txt .              # layer A - hiếm khi đổi
RUN pip install -r requirements.txt  # layer B - rất chậm (~60s)
COPY app.py .                        # layer C - đổi liên tục
```

Sửa `app.py` → chỉ layer C build lại, layer B vẫn dùng cache → build lại chỉ vài giây.

Nếu viết ngược lại (`COPY . .` rồi mới `pip install`), thì **sửa 1 dòng code bất kỳ cũng khiến `pip install` chạy lại từ đầu**. Nguyên tắc chung: xếp thứ tự các lệnh theo tần suất thay đổi, ít đổi nhất lên trên.

**4. CMD vs ENTRYPOINT khác nhau thế nào?**

| | `CMD` | `ENTRYPOINT` |
|---|---|---|
| Vai trò | Lệnh **mặc định**, chỉ là gợi ý | Lệnh **cố định**, luôn chạy |
| Khi `docker run img <args>` | Bị **thay thế hoàn toàn** | `<args>` được **nối thêm** vào sau |
| Dùng khi | Container đa năng, muốn override dễ | Container đóng vai 1 executable |

Cụ thể với `CMD ["python", "app.py"]` ở dòng 30:

```bash
docker run agent-develop              # chạy: python app.py
docker run agent-develop bash         # chạy: bash        <- CMD bị bỏ qua hoàn toàn
```

Nếu đổi thành `ENTRYPOINT ["python", "app.py"]`:

```bash
docker run agent-develop bash         # chạy: python app.py bash   <- bash thành tham số!
```

Cách dùng chuẩn là **kết hợp cả hai**: `ENTRYPOINT` giữ phần cố định, `CMD` làm tham số mặc định có thể override:

```dockerfile
ENTRYPOINT ["uvicorn", "main:app"]
CMD ["--host", "0.0.0.0", "--port", "8000"]
```

Chạy `docker run img --port 9000` sẽ thành `uvicorn main:app --port 9000`.

### Exercise 2.2: Build và run image develop

**Lệnh build** — bắt buộc chạy từ **thư mục gốc repo**, không phải từ trong `02-docker/develop`:

```bash
docker build -f 02-docker/develop/Dockerfile -t agent-develop .
docker run -d -p 8000:8000 --name agent-dev-test agent-develop
```

Lý do: dấu `.` cuối lệnh là **build context**. Dockerfile có `COPY utils/mock_llm.py utils/`, mà `utils/` nằm ở gốc repo — đứng trong thư mục con thì Docker không "nhìn" ra ngoài context được, build sẽ fail.

**Kết quả test:**

| Request | HTTP | Response |
|---|---|---|
| `GET /` | 200 | `{"message":"Agent is running in a Docker container!"}` |
| `GET /health` | 200 | `{"status":"ok","uptime_seconds":12.3,"container":true}` |
| `POST /ask?question=What is Docker` | 200 | `{"answer":"Container là cách đóng gói app để chạy ở mọi nơi..."}` |
| `POST /ask` + JSON body | **422** | `{"detail":[{"type":"missing","loc":["query","question"]}]}` |

Lỗi 422 ở dòng cuối lặp lại đúng anti-pattern #11 đã ghi ở Part 1: `02-docker/develop/app.py` dòng 21 viết `async def ask_agent(question: str)` — kiểu `str` trần khiến FastAPI hiểu là **query parameter**, không phải JSON body. Bản `production/main.py` dùng Pydantic model nên nhận body đúng cách.

### Exercise 2.3: Image size comparison

- **Develop:** 1660 MB (1.66 GB)
- **Production:** 237 MB
- **Difference:** giảm **85.7%** — nhỏ hơn **7 lần**

Yêu cầu của checklist là image < 500 MB → bản production **đạt** (237 MB).

> Ghi chú: `02-docker/README.md` dự đoán ~800 MB và ~160 MB. Số đo thực tế lệch khá nhiều (1.66 GB và 237 MB) vì tài liệu viết từ phiên bản base image cũ hơn; `python:3.11` hiện tại nền Debian trixie đã phình to hơn trước.

**Vì sao chênh lệch lớn đến vậy?** Dùng `docker history` xem từng layer:

`agent-develop` — nền `python:3.11` đầy đủ:

| Size | Layer |
|---|---|
| 134 MB | Debian base |
| 65 MB | apt: các gói cơ bản |
| 202 MB | apt: `buildpack-deps:curl` |
| **694 MB** | **apt: `buildpack-deps` — gcc, make, git, toàn bộ toolchain biên dịch** |
| 19.9 MB | apt |
| 70.5 MB | Biên dịch Python từ source |
| 51.8 MB | `pip install` dependencies của app |

`agent-production` — nền `python:3.11-slim` + multi-stage:

| Size | Layer |
|---|---|
| 87.4 MB | Debian slim base |
| 4.95 MB | apt: gói tối thiểu |
| 48.8 MB | Python runtime |
| **39.3 MB** | **`COPY --from=builder /root/.local` — chỉ site-packages đã cài xong** |
| ~90 KB | code app + utils + tạo user |

**Điểm mấu chốt:** layer **694 MB** chứa `gcc`, `make`, `git`… chỉ cần lúc **build**, không cần lúc **chạy**. Multi-stage build cài chúng ở stage `builder`, rồi stage `runtime` chỉ `COPY` sang đúng thư mục `site-packages` (39.3 MB). Toàn bộ stage `builder` bị **vứt bỏ**, không nằm trong image cuối.

Lợi ích không chỉ là dung lượng:

| | Develop | Production |
|---|---|---|
| Dung lượng | 1.66 GB | 237 MB |
| Thời gian pull khi deploy | Chậm (mạng 0.5 MB/s mất ~50 phút) | Nhanh hơn 7 lần |
| Có `gcc`, `git` trong image | ✅ Có — **rủi ro bảo mật** | ❌ Không |
| Chạy bằng user nào | `root` ❌ | `appuser` (non-root) ✅ |
| HEALTHCHECK | Không có | Có — Docker tự báo `(healthy)` |

Hai dòng cuối bảng là **bảo mật**, quan trọng không kém dung lượng. Kẻ tấn công chiếm được container có `gcc` thì có thể biên dịch mã độc ngay tại chỗ; chạy bằng `root` thì thoát container dễ hơn nhiều. Đã kiểm chứng:

```bash
$ docker exec agent-prod-test whoami
appuser

$ docker ps
agent-prod-test | Up 8 seconds (healthy)
```

**Test bản production — cả 4 endpoint đều 200:**

| Request | HTTP | Response |
|---|---|---|
| `GET /` | 200 | `{"app":"AI Agent","version":"2.0.0","environment":"production"}` |
| `GET /health` | 200 | `{"status":"ok","uptime_seconds":12.5,"version":"2.0.0",...}` |
| `GET /ready` | 200 | `{"ready":true}` |
| `POST /ask` + JSON body | 200 | `{"answer":"Container là cách đóng gói app..."}` |

### Exercise 2.4: Docker Compose stack

```bash
docker compose -f 02-docker/production/docker-compose.yml up -d
```

**Kiến trúc — 4 service:**

```
                    Internet
                       │
                       ▼
              ┌─────────────────┐
              │  nginx:alpine   │  ← service DUY NHẤT mở ra ngoài
              │  port 80, 443   │     reverse proxy + rate limit
              └────────┬────────┘
                       │  http://agent:8000
                       ▼
              ┌─────────────────┐
              │     agent       │  ← FastAPI, KHÔNG mở port ra host
              │  (non-root)     │
              └────┬───────┬────┘
                   │       │
         redis://redis:6379│http://qdrant:6333
                   ▼       ▼
            ┌──────────┐ ┌──────────┐
            │  redis   │ │  qdrant  │
            │  cache   │ │ vector DB│
            └──────────┘ └──────────┘

         Tất cả nằm trong network "internal" (bridge)
         Volume: redis_data, qdrant_data (giữ dữ liệu khi restart)
```

**Trạng thái sau khi khởi động:**

```
NAME                  SERVICE   STATUS                   PORTS
production-agent-1    agent     Up 29 seconds (healthy)  8000/tcp
production-nginx-1    nginx     Up 29 seconds            0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
production-qdrant-1   qdrant    Up 39 seconds (healthy)  6333-6334/tcp
production-redis-1    redis     Up 39 seconds (healthy)  6379/tcp
```

**Các service giao tiếp với nhau thế nào?**

Docker Compose tạo một **DNS nội bộ**: mỗi service được đăng ký bằng chính tên service của nó. Agent chỉ cần gọi `redis://redis:6379`, không cần biết địa chỉ IP. Đã kiểm chứng từ bên trong container agent:

```
redis:6379  -> OK (DNS: 172.18.0.3)
qdrant:6333 -> OK (DNS: 172.18.0.2)
```

IP do Docker cấp động, đổi mỗi lần restart — nên **phải dùng tên service**, hardcode IP là hỏng.

**Thứ tự khởi động được kiểm soát bằng `depends_on` + `condition: service_healthy`:**

```yaml
depends_on:
  redis:
    condition: service_healthy
  qdrant:
    condition: service_healthy
```

Agent chỉ khởi động **sau khi** redis và qdrant vượt qua healthcheck. Nếu chỉ viết `depends_on: [redis]` thì Compose chỉ đợi container *được tạo*, chứ không đợi Redis *sẵn sàng nhận lệnh* — agent sẽ crash vì kết nối vào lúc Redis còn đang khởi động.

**Kiểm chứng cách ly mạng — agent không lộ ra ngoài:**

```bash
$ curl http://localhost/health        # qua Nginx
{"status":"ok","uptime_seconds":37.0,"version":"2.0.0",...}   [200]

$ curl http://localhost:8000/health   # gọi thẳng agent
Không kết nối được
```

Trong `docker-compose.yml`, service `agent` **không có mục `ports:`** — chỉ nginx mới publish port ra host. Đây là mô hình bảo mật chuẩn: mọi traffic buộc phải đi qua reverse proxy, nơi đặt rate limiting và security headers.

**Security headers do Nginx tự thêm:**

```
Server: nginx                        ← ẩn số phiên bản (server_tokens off)
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
```

**Test rate limiting của Nginx** — cấu hình `rate=10r/s`, `burst=20 nodelay`:

```bash
# 60 request đồng thời, 30 luồng song song
$ seq 1 60 | xargs -P 30 -I{} curl -s -o /dev/null -w "%{http_code}\n" http://localhost/
```

| HTTP | Số request |
|---|---|
| 200 | 33 |
| **429** | **27** |

Request bị chặn nhận đúng JSON tuỳ chỉnh khai báo trong `nginx.conf`:

```json
{"error":"Too many requests","retry_after":1}
```

Lưu ý khi tự test: gọi `curl` **tuần tự** trong vòng lặp thì 40/40 đều trả 200, vì mỗi lần khởi động tiến trình `curl` mất vài chục mili giây khiến tốc độ thực tế không vượt ngưỡng. Phải bắn **song song** (`xargs -P`) mới chạm giới hạn.

**Test qua Nginx — cả 3 đều 200:**

| Request | HTTP | Response |
|---|---|---|
| `GET /health` | 200 | `{"status":"ok","uptime_seconds":37.0,...}` |
| `GET /` | 200 | `{"app":"AI Agent","version":"2.0.0","environment":"staging"}` |
| `POST /ask` | 200 | `{"answer":"Agent đang hoạt động tốt! (mock response)..."}` |

`environment` trả về `staging` — đúng giá trị đặt trong `docker-compose.yml`, chứng tỏ biến môi trường được truyền vào container thành công.

**Dọn dẹp:**

```bash
docker compose -f 02-docker/production/docker-compose.yml down          # giữ volume
docker compose -f 02-docker/production/docker-compose.yml down -v       # xoá cả volume
```

#### 2 lỗi phải sửa mới chạy được stack

**Lỗi 1 — thiếu file `.env.local`.** `docker-compose.yml` dòng 34–35 khai báo:

```yaml
env_file:
  - .env.local
```

Nhưng repo **không kèm file này** (đúng ra là vậy — nó chứa secret nên bị `.gitignore` chặn). Chạy `docker compose up` sẽ lỗi ngay: `env file .env.local not found`.

Đã tạo `02-docker/production/.env.local` với `OPENAI_API_KEY` để trống (dùng mock LLM) và `AGENT_API_KEY` giá trị dev. Đã kiểm tra file khớp pattern `.env.*` trong `.gitignore` nên không lọt lên Git.

**Lỗi 2 — khai báo `version` đã lỗi thời.** Compose in cảnh báo:

```
WARN: the attribute `version` is obsolete, it will be ignored
```

Từ Compose V2, dòng `version: "3.9"` ở đầu file không còn ý nghĩa.

**Đã sửa:** xoá dòng đó khỏi `02-docker/production/docker-compose.yml` và `05-scaling-reliability/production/docker-compose.yml`. Kiểm chứng bằng `docker compose config --quiet` — không còn cảnh báo nào.

**Đã bổ sung file mẫu `.env.local.example`** cho cả 2 thư mục. File `.env.local` thật chứa secret nên bị `.gitignore` chặn — nghĩa là ai clone repo về cũng gặp lỗi `env file .env.local not found` mà không biết cần điền gì. File `.example` giải quyết chuyện đó: copy ra là chạy được.

Kèm theo phải sửa `.gitignore`: pattern `.env.*` bắt luôn cả `.env.local.example`, khiến file hướng dẫn bị chặn oan. Đã thêm ngoại lệ `!*.example`, đồng thời kiểm tra lại 4 file `.env`/`.env.local` thật vẫn bị chặn đúng.

---

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment

- **URL:** https://day12-agent-production-5236.up.railway.app
- **Screenshots:** [dashboard.png](screenshots/dashboard.png) · [running.png](screenshots/running.png) · [health.png](screenshots/health.png) · [test.png](screenshots/test.png) · [ratelimit.png](screenshots/ratelimit.png) · [variables.png](screenshots/variables.png)
- **Platform:** Railway (gói Trial), project `day12-agent-ngothanhdat`, region `sfo`
- **Thư mục deploy:** `06-lab-complete/` — gồm 2 service: `day12-agent` (app) và `Redis` (database)

Deploy thành công, dịch vụ đang chạy. Toàn bộ kết quả test trên URL công khai (12/12 mục pass) nằm ở [DEPLOYMENT.md](DEPLOYMENT.md).

Bằng chứng quan trọng nhất — `GET /ready` trên cloud:

```json
{"ready": true, "storage": "redis"}
```

`"storage": "redis"` chứng minh agent trên cloud đang lưu bộ đếm rate limit và chi phí trong Redis dùng chung, đúng yêu cầu stateless. Nếu ra `"memory"` là chưa nối được Redis.

**⚠️ 3 vấn đề gặp phải khi deploy thật** (chi tiết cách xử lý ở [DEPLOYMENT.md](DEPLOYMENT.md)):

1. **`railway.toml` làm deploy chết ngay** — `startCommand` chứa `$PORT` nhưng Railway chạy lệnh ở dạng exec (không qua shell) nên `$PORT` không được thay thế. Lỗi: `Invalid value for '--port': '$PORT' is not a valid integer`. Sửa bằng cách bọc trong `sh -c '...'`.
2. **`railway up` deploy nhầm vào service Redis** — sau `railway add --database redis`, CLI tự link vào Redis. Phải tạo service app rồi mới `railway up --service <ten-app>`.
3. **Đặt biến môi trường xong phải `railway redeploy`** — container đang chạy không tự nạp biến mới.

**Đã verify trước khi deploy:** chạy `03-cloud-deployment/railway/app.py` ở local với `PORT=8100` để giả lập biến môi trường mà Railway inject.

```
GET  /       -> 200  {"message":"AI Agent running on Railway!","docs":"/docs","health":"/health"}
GET  /health -> 200  {"status":"ok","uptime_seconds":10.9,"platform":"Railway",...}
POST /ask    -> 200  {"question":"Am I on the cloud?","answer":"...","platform":"Railway"}
```

App **lắng nghe đúng cổng 8100** thay vì cổng 8000 mặc định → chứng minh dòng `port = int(os.getenv("PORT", 8000))` hoạt động. Đây là điều kiện sống còn: Railway/Render cấp cổng ngẫu nhiên qua biến `PORT`, app nào hardcode cổng sẽ bị đánh dấu unhealthy và platform restart vô hạn.

**Lệnh deploy:**

```bash
cd 03-cloud-deployment/railway
npm i -g @railway/cli
railway login          # mở trình duyệt
railway init
railway up
railway domain         # lấy public URL
```

**⚠️ Lưu ý — `CODE_LAB.md` có 2 chỗ sai ở phần này:**

*1. Đừng chạy `railway variables set PORT=8000`.* `CODE_LAB.md` bước 4 bảo set biến này, nhưng chính `railway.toml` lại ghi *"Railway inject PORT tự động"*. Set tay sẽ ép app nghe cổng 8000 trong khi Railway route traffic tới cổng khác → healthcheck fail, deploy hỏng. **Để Railway tự quản lý `PORT`.**

*2. Cú pháp `railway variables set KEY=value` đã lỗi thời.* Railway CLI bản mới dùng:

```bash
railway variables --set "AGENT_API_KEY=my-secret-key"
```

### Exercise 3.2: So sánh `render.yaml` với `railway.toml`

| Tiêu chí | `railway.toml` | `render.yaml` |
|---|---|---|
| Định dạng | TOML | YAML |
| Phạm vi khai báo | **Chỉ 1 service** | **Nhiều service** trong 1 file (web + redis) |
| Khai báo biến môi trường | ❌ Không — phải set qua CLI/dashboard | ✅ Có, ngay trong file (mục `envVars`) |
| Cách build | `builder = "NIXPACKS"` tự đoán ngôn ngữ | `buildCommand` viết tay tường minh |
| Health check | `healthcheckPath` + `healthcheckTimeout` | `healthCheckPath` |
| Chính sách restart | `restartPolicyType`, `restartPolicyMaxRetries` | ❌ Không có — Render tự xử lý |
| Chọn region | ❌ Không | ✅ `region: singapore` |
| Chọn gói dịch vụ | ❌ Không | ✅ `plan: free` |
| Tự deploy khi push | Mặc định bật | `autoDeploy: true` |
| Quản lý secret | Chỉ qua CLI/dashboard | `sync: false` (nhập tay) hoặc `generateValue: true` (Render tự sinh) |

**Khác biệt cốt lõi:** `render.yaml` là **Infrastructure as Code đầy đủ** — mô tả trọn vẹn hạ tầng gồm cả Redis, region, gói cước, biến môi trường. Xoá hết rồi deploy lại từ file này là dựng lại y nguyên.

`railway.toml` chỉ mô tả **cách chạy app**; phần hạ tầng còn lại (thêm Redis, chọn region) phải bấm tay trên dashboard.

Hai cơ chế secret của Render đáng chú ý:
- `sync: false` — Render biết cần biến này nhưng **không lấy giá trị từ file**, bắt nhập tay trên dashboard. Tránh lỡ tay commit secret.
- `generateValue: true` — Render **tự sinh chuỗi ngẫu nhiên**. Rất hợp với `AGENT_API_KEY`: không ai, kể cả lập trình viên, biết giá trị cho tới khi mở dashboard xem.

> **✅ Đã sửa `03-cloud-deployment/railway/railway.toml`:** file này dính đúng lỗi `$PORT` đã làm chết deploy ở Part 6 — Railway chạy `startCommand` dạng exec nên `$PORT` không được thay thế. Đã bọc trong `sh -c '...'`.
>
> Riêng `render.yaml` thì **giữ nguyên**, vì Render chạy `startCommand` **qua shell**, `$PORT` được thay bình thường. Đây là khác biệt thật giữa 2 nền tảng, sửa nhầm chỗ đang đúng còn tệ hơn.

> **⚠️ Phát hiện:** thư mục `03-cloud-deployment/render/` **chỉ có đúng file `render.yaml`**, thiếu `app.py` và `requirements.txt`. Trong khi `render.yaml` khai báo `buildCommand: pip install -r requirements.txt` và `startCommand: uvicorn app:app`. Deploy y nguyên thư mục này sẽ fail vì không có gì để build. Thêm nữa, Render yêu cầu `render.yaml` nằm ở **gốc repository** mới nhận diện được blueprint. Việc deploy thật sẽ làm ở Part 6 với thư mục `06-lab-complete/` — nơi có đủ code lẫn config.

### Exercise 3.3: (Optional) GCP Cloud Run — đọc hiểu CI/CD pipeline

**`cloudbuild.yaml` — pipeline 4 bước, chạy tự động khi push lên nhánh main:**

```
test  ──>  build  ──>  push  ──>  deploy
```

Các bước nối với nhau bằng `waitFor`, tạo thành chuỗi tuần tự. Bước `test` fail thì dừng luôn, **không có image hỏng nào lên được production** — đây chính là giá trị của CI/CD.

| Bước | Chạy trong image | Làm gì |
|---|---|---|
| `test` | `python:3.11-slim` | `pip install` + `pytest` |
| `build` | `gcr.io/cloud-builders/docker` | Build, gắn 2 tag: `$COMMIT_SHA` và `latest` |
| `push` | `gcr.io/cloud-builders/docker` | Đẩy lên Container Registry |
| `deploy` | `gcr.io/cloud-builders/gcloud` | `gcloud run deploy` |

Vài chi tiết đáng học:

- **Gắn 2 tag cùng lúc.** `$COMMIT_SHA` cho phép truy vết chính xác image nào ứng với commit nào, và rollback bằng cách deploy lại tag cũ. `latest` để `--cache-from` tận dụng layer cache của lần build trước, rút ngắn thời gian build.
- **`--min-instances=1`** giữ luôn 1 instance sống để tránh **cold start** — Cloud Run mặc định scale về 0 khi không có traffic, request đầu tiên sau đó phải chờ khởi động container. Đánh đổi: trả tiền 24/7 cho instance đó.
- **`--max-instances=10`** chặn hoá đơn. Không có nó, một đợt traffic đột biến (hoặc bị tấn công) có thể scale lên hàng trăm instance.
- **`--set-secrets=OPENAI_API_KEY=openai-key:latest`** lấy secret từ **Secret Manager** lúc chạy, không nhúng vào image. Đúng bài học từ Part 1.

**`service.yaml` — khai báo service theo chuẩn Knative:**

Điểm hay nhất là dùng **2 loại probe khác nhau**, đúng như phân biệt `/health` và `/ready` đã học:

```yaml
livenessProbe:            # "còn sống không?" -> chết thì restart
  httpGet: {path: /health, port: 8000}
  initialDelaySeconds: 10
  periodSeconds: 30

startupProbe:             # "khởi động xong chưa?" -> chờ tới 30s
  httpGet: {path: /ready, port: 8000}
  initialDelaySeconds: 5
  failureThreshold: 10
  periodSeconds: 3
```

`startupProbe` cho phép thử lại 10 lần, mỗi lần cách 3 giây → tổng cộng chờ được **30 giây** để app khởi động. Trong lúc đó `livenessProbe` **chưa chạy**. Không có `startupProbe`, app nào khởi động chậm (load model AI chẳng hạn) sẽ bị `livenessProbe` giết ngay trước khi kịp sẵn sàng → kẹt vòng lặp restart vĩnh viễn.

`containerConcurrency: 80` — mỗi instance nhận tối đa 80 request đồng thời rồi Cloud Run mới bật instance mới. Đây là khác biệt lớn so với AWS Lambda (1 request/instance).

---

## Part 4: API Security

### Exercise 4.1-4.3: Test results

#### Exercise 4.1 — API Key authentication

File: `04-api-gateway/develop/app.py`

**Trả lời 3 câu hỏi của đề bài:**

*1. API key được check ở đâu?*

Ở hàm `verify_api_key()` (dòng 39–54), được gắn vào endpoint bằng cơ chế **dependency injection** của FastAPI:

```python
@app.post("/ask")
async def ask_agent(request: Request, _key: str = Depends(verify_api_key)):
```

Ưu điểm: logic kiểm tra viết **một lần**, muốn bảo vệ endpoint nào thì thêm `Depends(verify_api_key)` vào endpoint đó. Không lặp code, và nhìn chữ ký hàm là biết ngay endpoint có được bảo vệ hay không.

*2. Điều gì xảy ra nếu sai key?*

Code phân biệt **2 tình huống khác nhau** — chi tiết nhỏ nhưng đúng chuẩn HTTP:

| Tình huống | HTTP | Ý nghĩa |
|---|---|---|
| Không gửi header `X-API-Key` | **401** Unauthorized | "Bạn chưa xưng danh" |
| Gửi nhưng key sai | **403** Forbidden | "Đã xưng danh nhưng không có quyền" |

*3. Làm sao rotate key?*

Hiện tại `API_KEY = os.getenv("AGENT_API_KEY", ...)` chỉ đọc **một** key duy nhất lúc khởi động. Muốn đổi key phải restart app → **gián đoạn dịch vụ**, và mọi client phải đổi key cùng lúc.

Cách làm đúng là chấp nhận **nhiều key song song** để xoay vòng không downtime:

```python
VALID_KEYS = set(os.getenv("AGENT_API_KEYS", "").split(","))

def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if not api_key:
        raise HTTPException(401, "Missing API key")
    if api_key not in VALID_KEYS:
        raise HTTPException(403, "Invalid API key")
    return api_key
```

Quy trình xoay key: thêm key mới vào danh sách → báo client chuyển sang key mới → gỡ key cũ. Không lúc nào dịch vụ bị gián đoạn.

**Kết quả test:**

```bash
AGENT_API_KEY=my-secret-key python -m uvicorn app:app --port 8000
```

| # | Tình huống | HTTP | Response |
|---|---|---|---|
| 1 | Không có key | **401** | `{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}` |
| 2 | Key sai | **403** | `{"detail":"Invalid API key."}` |
| 3 | Key đúng | **200** | `{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock)..."}` |
| 4 | `GET /` (public) | 200 | `{"message":"AI Agent API","auth":"Required for /ask"}` |
| 5 | `GET /health` (public) | 200 | `{"status":"ok"}` |

Hai endpoint cuối **cố ý để public**: platform phải gọi được `/health` mà không cần key, nếu không nó sẽ tưởng app chết và restart container liên tục.

#### Exercise 4.2 — JWT authentication

**⚠️ `CODE_LAB.md` sai 2 chỗ ở bài này:**

| Tài liệu ghi | Thực tế trong code |
|---|---|
| `POST /token` | `POST /auth/token` |
| `{"username":"admin","password":"secret"}` | `student/demo123` hoặc `teacher/teach456` |

Làm theo đúng tài liệu sẽ nhận 404 rồi 401. Tài khoản thật khai báo ở `auth.py` dòng 27–30.

**Luồng JWT:**

```
1. POST /auth/token  {username, password}
                ↓  authenticate_user() so khớp DEMO_USERS
                ↓  create_token() ký payload bằng SECRET_KEY (HS256)
        ← {"access_token": "eyJhbGci..."}

2. POST /ask  header: Authorization: Bearer eyJhbGci...
                ↓  verify_token() kiểm tra chữ ký + hạn dùng
                ↓  lấy ra username + role
        ← kết quả
```

**Kết quả test:**

| Tình huống | HTTP | Response |
|---|---|---|
| Sai mật khẩu | **401** | `{"detail":"Invalid credentials"}` |
| Đúng mật khẩu | 200 | `{"access_token":"eyJhbGciOiJIUzI1NiIs...","token_type":"bearer"}` |
| `/ask` không token | **401** | `{"detail":"Authentication required. Include: Authorization: Bearer <token>"}` |
| `/ask` có token | 200 | `{"question":"Explain JWT","answer":"...","usage":{...}}` |
| `/ask` token giả | **403** | `{"detail":"Invalid token."}` |

**Bên trong token có gì?** Phần giữa của JWT là Base64, **giải mã được mà không cần secret**:

```json
{
  "sub": "student",
  "role": "user",
  "iat": 1786333042,
  "exp": 1786336642
}
```

Đây là điểm **cực kỳ quan trọng** hay bị hiểu nhầm: JWT chỉ được **ký**, **không được mã hoá**. Ai chặn được token đều đọc được nội dung bên trong. Chữ ký chỉ đảm bảo *không sửa được* nội dung, chứ không giấu được nó.

→ **Tuyệt đối không nhét mật khẩu, số thẻ, thông tin nhạy cảm vào JWT payload.**

**Vì sao JWT gọi là stateless?** Server không lưu token ở đâu cả. Mỗi request, server chỉ dùng `SECRET_KEY` xác minh chữ ký là biết token thật hay giả — **không cần truy vấn database**. Nhờ vậy chạy bao nhiêu instance cũng được, instance nào cũng verify được token do instance khác cấp.

Đánh đổi: **không thu hồi token trước hạn được**. Token đã cấp thì có hiệu lực đến khi `exp` hết. Muốn thu hồi ngay phải có blacklist trong Redis — nhưng làm vậy là mất tính stateless.

#### Exercise 4.3 — Rate limiting

**Trả lời 3 câu hỏi của đề bài:**

*1. Thuật toán nào?* **Sliding Window Log** (`rate_limiter.py` dòng 29–71).

Mỗi user có một `deque` lưu **mốc thời gian của từng request**. Trước khi xử lý, code xoá các mốc đã ra khỏi cửa sổ 60 giây rồi đếm phần còn lại:

```python
while window and window[0] < now - self.window_seconds:
    window.popleft()
```

So với **Fixed Window** (đếm theo phút chẵn), Sliding Window không dính lỗi *burst ở ranh giới* — kiểu gửi 10 request lúc 10:00:59 và 10 request nữa lúc 10:01:01, tổng 20 request trong 2 giây mà vẫn lọt.

Đánh đổi: tốn RAM hơn vì phải lưu từng mốc thời gian, thay vì chỉ một biến đếm.

*2. Giới hạn bao nhiêu?* Khai báo ở dòng 86–87:

```python
rate_limiter_user  = RateLimiter(max_requests=10,  window_seconds=60)   # user:  10/phút
rate_limiter_admin = RateLimiter(max_requests=100, window_seconds=60)   # admin: 100/phút
```

*3. Làm sao admin vượt giới hạn?* Chọn limiter theo `role` lấy từ JWT (`app.py` dòng 141):

```python
limiter = rate_limiter_admin if role == "admin" else rate_limiter_user
```

Vì `role` nằm trong token đã ký, client **không tự sửa thành admin được** — sửa một ký tự là chữ ký sai, `verify_token()` trả 403 ngay.

**Kết quả test — bắn 15 request:**

*Tài khoản `student` (role = user, giới hạn 10/phút):*

```
req  1 -> 200  còn lại 9        req  9 -> 200  còn lại 1
req  2 -> 200  còn lại 8        req 10 -> 200  còn lại 0
req  3 -> 200  còn lại 7        req 11 -> 429  retry_after_seconds: 39
req  4 -> 200  còn lại 6        req 12 -> 429  retry_after_seconds: 37
req  5 -> 200  còn lại 5        req 13 -> 429  retry_after_seconds: 35
req  6 -> 200  còn lại 4        req 14 -> 429  retry_after_seconds: 33
req  7 -> 200  còn lại 3        req 15 -> 429  retry_after_seconds: 31
req  8 -> 200  còn lại 2
                                TỔNG: 10 x 200, 5 x 429
```

*Tài khoản `teacher` (role = admin, giới hạn 100/phút):*

```
TỔNG: 15 x 200, 0 x 429      <- không bị chặn, đúng như thiết kế
```

Response 429 kèm đủ thông tin để client tự xử lý:

```json
{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":39}
```

Chú ý `retry_after_seconds` **giảm dần** 39 → 37 → 35 → 33 → 31. Đó là bằng chứng cửa sổ đang **trượt**: nó tính từ mốc request cũ nhất còn trong cửa sổ, chứ không phải một mốc cố định.

**Phân quyền cũng đã test:**

| Request | HTTP | Kết quả |
|---|---|---|
| `teacher` gọi `/admin/stats` | 200 | `{"global_cost_usd":0.000457,"global_budget_usd":10.0}` |
| `student` gọi `/admin/stats` | **403** | `{"detail":"Admin only"}` |

### Exercise 4.4: Cost guard implementation

**Vì sao bản có sẵn chưa dùng được cho production?**

`cost_guard.py` lưu chi tiêu trong dict Python (`self._records`) — nằm trong RAM của **một tiến trình**. Hai vấn đề chí mạng:

```
Budget $10/tháng, chạy 3 instance sau load balancer:

  Instance 1: sổ riêng, cho tiêu $10
  Instance 2: sổ riêng, cho tiêu $10     →  thực tế tiêu $30 mới bị chặn
  Instance 3: sổ riêng, cho tiêu $10

Restart container → mất sạch số liệu → user tiêu lại từ đầu.
```

**Lời giải — file mới `04-api-gateway/production/cost_guard_redis.py`:**

```python
def _month_key(user_id: str) -> str:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return f"budget:{user_id}:{month}"        # budget:student:2026-08


def check_budget(user_id: str, estimated_cost: float = 0.0) -> bool:
    """Chỉ ĐỌC, không ghi. Vượt budget thì raise 402."""
    current = float(r.get(_month_key(user_id)) or 0.0)
    if current + estimated_cost > MONTHLY_BUDGET_USD:
        raise HTTPException(402, detail={
            "error": "Monthly budget exceeded",
            "used_usd": round(current, 6),
            "budget_usd": MONTHLY_BUDGET_USD,
            "resets_at": "đầu tháng sau (UTC)",
        })
    return True


def record_cost(user_id: str, cost_usd: float) -> float:
    """Ghi nhận chi phí SAU khi gọi LLM xong."""
    key = _month_key(user_id)
    total = r.incrbyfloat(key, cost_usd)      # atomic
    r.expire(key, 32 * 24 * 3600)             # lưới an toàn
    return float(total)
```

**Ba quyết định thiết kế đáng chú ý:**

*1. Gắn tháng vào tên key → "reset đầu tháng" xảy ra tự động.*

Key có dạng `budget:student:2026-08`. Sang tháng 9, key đổi thành `budget:student:2026-09` — Redis chưa có key đó nên `GET` trả `None`, chi tiêu về 0. **Không cần cron job, không cần lệnh xoá thủ công.** Ít thành phần chuyển động thì ít chỗ hỏng.

*2. Dùng `INCRBYFLOAT` thay vì `GET` → cộng → `SET`.*

Đây là điểm quan trọng nhất. `INCRBYFLOAT` là thao tác **atomic** — Redis xử lý tuần tự từng lệnh. Nếu viết kiểu đọc-rồi-ghi:

```
Instance A: GET  -> 5.0                    Instance B: GET -> 5.0
Instance A: tính 5.0 + 2 = 7.0             Instance B: tính 5.0 + 3 = 8.0
Instance A: SET 7.0                        Instance B: SET 8.0   ← đè mất $2
```

Hai instance cùng chạy sẽ **mất tiền** do race condition. `INCRBYFLOAT` không dính lỗi này.

*3. Tách `check_budget()` (chỉ đọc) khỏi `record_cost()` (chỉ ghi).*

Kiểm tra budget **trước** khi gọi LLM, ghi nhận chi phí **sau** khi có kết quả. Nếu LLM lỗi giữa chừng thì không bị trừ tiền oan.

**Kết quả test — 8/8 pass:**

| # | Nội dung | Kết quả |
|---|---|---|
| 1 | Kết nối Redis | `ping() = True` |
| 2 | Trạng thái ban đầu | `used=$0.0  remaining=$10.0  0.0%` |
| 3 | Cộng dồn `$2.5 + $3.0 + $1.5` | `used=$7.0  remaining=$3.0  70.0%` |
| 4 | Còn budget thì cho qua | `check_budget($1.0) = True` (7+1=8 < 10) |
| 5 | Vượt budget thì chặn | **HTTP 402** `Monthly budget exceeded` (7+5=12 > 10) |
| 6 | Cảnh báo ở mốc 80% | `used=$8.5 (85.0%)  near_limit=True` |
| 7 | Key gắn tháng + TTL | `budget:test-student:2026-08`, TTL 2.764.800s (~32 ngày) |
| 8 | Dữ liệu nằm trong Redis | `GET budget:test-student:2026-08 = 8.5` |

Test 8 là bằng chứng quan trọng nhất: đọc thẳng từ Redis bằng lệnh `GET` vẫn thấy số liệu. Nghĩa là restart app hay chạy 3 instance đều dùng chung một sổ.

**Vì sao dùng HTTP 402?** `402 Payment Required` là mã HTTP mô tả đúng tình huống "hết tiền". Phân biệt rõ với **429** (gọi quá nhanh — chờ chút rồi thử lại được) và **403** (không có quyền — chờ bao lâu cũng vô ích). Client nhìn mã là biết phải làm gì.

#### Bug đã sửa trong `04-api-gateway/production/app.py`

Response của `/ask` có field đặt sai tên:

```python
"budget_remaining_usd": usage.total_cost_usd,     # ❌ đây là số ĐÃ TIÊU
```

Biến `usage.total_cost_usd` là **chi phí đã dùng**, nhưng lại gán vào field tên *remaining* (còn lại). Client đọc `budget_remaining_usd: 0.000293` sẽ tưởng sắp hết tiền, trong khi thực tế mới tiêu chưa tới 1 xu trên budget $1.

**Đã sửa:**

```python
"budget_used_usd": usage.total_cost_usd,
"budget_remaining_usd": round(
    max(0.0, cost_guard.daily_budget_usd - usage.total_cost_usd), 6
),
```

Kiểm chứng sau khi sửa:

```json
{"requests_remaining": 99, "budget_used_usd": 1.9e-05, "budget_remaining_usd": 0.999981}
```

---

## Part 5: Scaling & Reliability

### Exercise 5.1-5.5: Implementation notes

#### Exercise 5.1 — Health checks

Đề bài yêu cầu implement `/health` và `/ready`. File `05-scaling-reliability/develop/app.py` **đã có sẵn cả hai** (dòng 104–168), nên nhiệm vụ ở đây là đọc hiểu và kiểm chứng.

**`/health` — Liveness probe:**

```json
{
  "status": "ok",
  "uptime_seconds": 7.0,
  "version": "1.0.0",
  "environment": "development",
  "timestamp": "2026-08-10T03:45:50.091889+00:00",
  "checks": {
    "memory": {"status": "ok", "used_percent": 54.2}
  }
}
```

> Lần chạy đầu, `checks.memory` trả về `{"status":"ok","note":"psutil not installed"}` vì mình chưa cài `psutil` — thư viện này **có** trong `requirements.txt` nhưng bị bỏ sót. Sau khi `pip install psutil==6.0.0` thì endpoint báo đúng mức RAM 54.2%.
>
> Đáng chú ý là code không crash khi thiếu thư viện, nhờ khối `try/except ImportError` ở dòng 123–131. Đây là cách viết health check đúng: **bản thân health check không bao giờ được phép làm sập app**.

**`/ready` — Readiness probe:**

```json
{"ready": true, "in_flight_requests": 1}
```

**Vì sao phải tách làm 2 endpoint?**

| | `/health` (liveness) | `/ready` (readiness) |
|---|---|---|
| Câu hỏi | "Tiến trình còn sống không?" | "Nhận request được chưa?" |
| Ai gọi | Platform (Railway, K8s) | Load balancer / Nginx |
| Fail thì sao | **Restart container** | **Ngừng đẩy traffic vào**, không restart |
| Ví dụ fail | Deadlock, hết RAM | Đang khởi động, mất kết nối Redis |

Hậu quả thật khi nhầm lẫn: nếu `/health` cũng kiểm tra Redis, thì **Redis chớp nhoáng gián đoạn 5 giây** sẽ khiến platform restart **toàn bộ** container cùng lúc. Một sự cố nhỏ ở tầng cache biến thành sập toàn hệ thống. Đúng ra chỉ `/ready` mới được kiểm tra dependency bên ngoài.

Trường `in_flight_requests` do middleware ở dòng 72–81 đếm:

```python
@app.middleware("http")
async def track_requests(request, call_next):
    global _in_flight_requests
    _in_flight_requests += 1
    try:
        return await call_next(request)
    finally:
        _in_flight_requests -= 1     # finally: giảm kể cả khi request lỗi
```

Từ khoá `finally` rất quan trọng — nếu request ném exception mà không giảm biến đếm, con số sẽ phình lên mãi và app không bao giờ chịu shutdown.

#### Exercise 5.2 — Graceful shutdown

Đề bài yêu cầu implement signal handler. File develop **đã có sẵn** (dòng 175–187) và có thêm phần chờ request hoàn thành trong `lifespan` (dòng 54–66):

```python
# ── Shutdown ──
_is_ready = False                     # 1. báo LB ngừng gửi traffic mới
logger.info("🔄 Graceful shutdown initiated...")

timeout = 30                          # 2. chờ request đang chạy xong
elapsed = 0
while _in_flight_requests > 0 and elapsed < timeout:
    logger.info(f"Waiting for {_in_flight_requests} in-flight requests...")
    time.sleep(1)
    elapsed += 1

logger.info("✅ Shutdown complete")    # 3. thoát
```

Điểm tinh tế: `_is_ready = False` được đặt **trước** vòng chờ. Nhờ vậy `/ready` lập tức trả 503, load balancer thấy vậy sẽ ngừng gửi request mới vào instance này, trong khi các request cũ vẫn được xử lý nốt. Không có bước này thì vừa chờ vừa nhận thêm request mới, không bao giờ shutdown xong.

`timeout = 30` là lưới an toàn: nếu có request treo, sau 30 giây vẫn thoát chứ không chờ vô hạn.

**Vì sao SIGTERM quan trọng?**

| Signal | Bắt được? | Ai gửi | Hậu quả |
|---|---|---|---|
| **SIGTERM** | ✅ Có | Platform khi deploy/scale down | App kịp dọn dẹp |
| **SIGKILL** | ❌ Không | Platform sau khi hết hạn chờ | Chết ngay, request đang chạy mất trắng |

Quy trình chuẩn khi deploy bản mới: platform gửi `SIGTERM` → chờ (Kubernetes mặc định 30s) → nếu chưa thoát thì `SIGKILL`. App xử lý SIGTERM tử tế = **deploy không downtime**. App không xử lý = user đang gọi API nhận lỗi 502.

> **Ghi chú về môi trường test:** Windows **không có SIGTERM thật** — `os.kill()` trên Windows thực chất gọi `TerminateProcess`, tương đương SIGKILL, nên không thể demo graceful shutdown đúng cách trên host. Vì vậy phần này được kiểm chứng **bên trong container Linux** bằng lệnh `docker stop` (Docker gửi SIGTERM thật, chờ 10 giây rồi mới SIGKILL).

**Kiểm chứng thật trong container:**

```bash
$ time docker stop production-agent-1

production-agent-1
real    0m0.629s          ← chỉ 0,63 giây
```

**Đây chính là bằng chứng.** Docker gửi SIGTERM rồi chờ tối đa 10 giây mới dùng SIGKILL. Container thoát sau **0,63 giây** nghĩa là nó **tự nguyện thoát** khi nhận SIGTERM. Nếu app phớt lờ tín hiệu, lệnh này sẽ mất đúng 10 giây rồi container bị giết cứng.

Log của instance vừa dừng cho thấy đủ chuỗi các bước:

```
INFO:     Shutting down
INFO:     Waiting for application shutdown.
INFO:app:Instance instance-20c5e0 shutting down     ← hàm lifespan shutdown đã chạy
INFO:     Application shutdown complete.
INFO:     Finished server process [1]
```

#### Exercise 5.3 — Stateless design

**Anti-pattern (lưu state trong RAM):**

```python
conversation_history = {}          # ❌ dict trong RAM của MỘT tiến trình

@app.post("/ask")
def ask(user_id: str, question: str):
    history = conversation_history.get(user_id, [])
```

**Cách đúng (lưu state trong Redis):**

```python
def save_session(session_id, session, ttl_seconds=3600):
    _redis.setex(f"session:{session_id}", ttl_seconds, json.dumps(session))

def load_session(session_id):
    data = _redis.get(f"session:{session_id}")
    return json.loads(data) if data else None
```

**Vì sao bắt buộc phải vậy?** Vì load balancer chia request ngẫu nhiên:

```
        Request 1  ──> Instance A   (lưu history vào RAM của A)
        Request 2  ──> Instance B   (RAM của B trống → "bạn là ai?")
        Request 3  ──> Instance C   (RAM của C trống → quên tiếp)
```

Người dùng sẽ thấy agent **mất trí nhớ ngẫu nhiên** — lúc nhớ lúc quên tuỳ vào request rơi vào instance nào. Lỗi này cực khó debug vì chạy 1 instance ở máy local thì không bao giờ tái hiện được.

Đưa state ra Redis thì mọi instance đọc chung một chỗ, instance trở thành thứ **dùng xong vứt đi được** — muốn thêm, bớt, restart lúc nào cũng được.

#### Exercise 5.4 — Load balancing

```bash
docker compose up -d --build --scale agent=3
```

**Trạng thái stack:**

```
NAME                 STATUS                   PORTS
production-agent-1   Up 37 seconds (healthy)  8000/tcp
production-agent-2   Up 37 seconds (healthy)  8000/tcp
production-agent-3   Up 37 seconds (healthy)  8000/tcp
production-nginx-1   Up 36 seconds            0.0.0.0:8080->80/tcp
production-redis-1   Up 48 seconds (healthy)  6379/tcp
```

**Nginx phân tán thế nào?** Bắn 12 request qua cổng 8080:

```
req  1 -> instance-ef94a9      req  7 -> instance-ef94a9
req  2 -> instance-ca241d      req  8 -> instance-ca241d
req  3 -> instance-20c5e0      req  9 -> instance-20c5e0
req  4 -> instance-ef94a9      req 10 -> instance-ef94a9
req  5 -> instance-ca241d      req 11 -> instance-ca241d
req  6 -> instance-20c5e0      req 12 -> instance-20c5e0
```

**Round-robin chính xác tuyệt đối** — xoay vòng đều 3 instance, mỗi instance nhận đúng 4 request.

Điều thú vị là `nginx.conf` chỉ khai báo **một** dòng upstream:

```nginx
upstream agent_cluster {
    server agent:8000;
    keepalive 16;
}
```

Không hề liệt kê 3 instance. Docker Compose đăng ký tên `agent` trong DNS nội bộ trỏ tới **cả 3 địa chỉ IP**, Nginx phân giải ra rồi tự xoay vòng. Nhờ vậy `--scale agent=5` cũng chạy ngay, không phải sửa config.

**Chịu lỗi:**

```nginx
proxy_next_upstream error timeout http_503;
proxy_next_upstream_tries 3;
```

Instance nào lỗi hoặc trả 503 thì Nginx **tự thử instance khác**, người dùng không thấy lỗi.

#### Exercise 5.5 — Test stateless

```bash
python test_stateless.py
```

**Kết quả — 5 request rơi vào 3 instance khác nhau:**

```
Session ID: 554d8595-4e7a-4745-80af-bb66577afdc9

Request 1: [instance-ef94a9]  Q: What is Docker?
Request 2: [instance-ca241d]  Q: Why do we need containers?
Request 3: [instance-20c5e0]  Q: What is Kubernetes?
Request 4: [instance-ef94a9]  Q: How does load balancing work?
Request 5: [instance-ca241d]  Q: What is Redis used for?

Instances used: {'instance-20c5e0', 'instance-ef94a9', 'instance-ca241d'}

--- Conversation History ---
Total messages: 10        ← đủ 5 cặp hỏi–đáp, không sót câu nào
```

**Phép thử khắc nghiệt hơn — giết hẳn một instance rồi hỏi tiếp:**

```bash
$ docker stop production-agent-1      # chính là instance-20c5e0

$ docker compose ps
production-agent-2 | Up About a minute (healthy)
production-agent-3 | Up About a minute (healthy)      ← chỉ còn 2
```

Gửi tiếp 3 request vào **đúng session cũ**:

```
req 6 -> instance-ca241d
req 7 -> instance-ef94a9
req 8 -> instance-ca241d
```

Kiểm tra lại lịch sử hội thoại:

```
Tổng cộng: 16 tin nhắn (trước đó là 10)
3 tin nhắn cuối:
  [assistant]: Agent đang hoạt động tốt! (mock response)...
  [user]:      Cau hoi tiep theo 8...
  [assistant]: Agent đang hoạt động tốt! (mock response)...
```

**Toàn bộ hội thoại còn nguyên** dù instance từng phục vụ nó đã chết hẳn. Nginx tự động chuyển traffic sang 2 instance còn sống, và chúng đọc được lịch sử vì dữ liệu nằm ở Redis chứ không ở RAM instance nào.

Đây chính là ý nghĩa của **stateless**: instance chỉ là chỗ chạy code, không phải chỗ giữ dữ liệu.

#### Tối ưu đã thực hiện: bỏ `gcc` khỏi Dockerfile

`05-scaling-reliability/production/Dockerfile` cài build tools ở stage builder:

```dockerfile
RUN apt-get update && apt-get install -y gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*
```

Nhưng `requirements.txt` chỉ có `fastapi`, `uvicorn[standard]`, `redis` — **cả ba đều có wheel dựng sẵn** cho manylinux/CPython 3.11. Pip tải wheel về là dùng được ngay, không biên dịch gì cả.

Lần build đầu, riêng bước này tải hơn 200 MB (`gcc-14-x86-64-linux-gnu` một mình đã 21,4 MB) và chạy hơn 4 phút mà không phục vụ mục đích nào.

**Đã bỏ khối `apt-get` đó.** Build lại thành công, cả 3 instance `healthy`, mọi test ở trên đều chạy sau khi sửa. Chỉ nên thêm lại `gcc` khi requirements có package thật sự phải compile.

#### Lỗi phải sửa mới chạy được stack

Giống Part 2: `docker-compose.yml` khai báo `env_file: - .env.local` nhưng repo không kèm file này. Đã tạo `05-scaling-reliability/production/.env.local`, đã kiểm tra bị `.gitignore` chặn.

---

## Part 6: Final Project

### Kết quả nghiệm thu

```
python check_production_ready.py

  Result: 20/20 checks passed (100%)
  🎉 PRODUCTION READY! Deploy nào!
```

Image cuối cùng: **248 MB** — yêu cầu của checklist là dưới 500 MB.

### Cấu trúc thư mục — khớp yêu cầu `DAY12_DELIVERY_CHECKLIST.md`

```
06-lab-complete/
├── app/
│   ├── __init__.py
│   ├── main.py            # chỉ lo phần HTTP
│   ├── config.py          # đọc config từ env
│   ├── auth.py            # ✨ tách mới
│   ├── rate_limiter.py    # ✨ tách mới
│   ├── cost_guard.py      # ✨ tách mới
│   └── storage.py         # ✨ tách mới — kết nối Redis dùng chung
├── utils/
│   ├── __init__.py
│   └── mock_llm.py        # ✨ thêm mới
├── Dockerfile             # multi-stage, non-root, HEALTHCHECK
├── docker-compose.yml     # ✨ viết lại: agent + redis + nginx
├── nginx.conf             # ✨ thêm mới — load balancer
├── requirements.txt
├── .env.example
├── .dockerignore
├── railway.toml + render.yaml
└── check_production_ready.py
```

Ban đầu repo chỉ có `main.py` và `config.py`, mọi logic gộp chung một file. Checklist yêu cầu tách riêng `auth.py`, `rate_limiter.py`, `cost_guard.py` và có `utils/mock_llm.py`.

Thêm `storage.py` ngoài yêu cầu, vì cả `rate_limiter` lẫn `cost_guard` đều cần Redis — để mỗi file tự gọi `redis.from_url()` sẽ tạo hai connection pool riêng, lãng phí và khó kiểm soát.

### Nâng cấp quan trọng nhất: từ in-memory sang Redis

Code gốc đếm rate limit và chi phí bằng biến toàn cục trong RAM:

```python
_rate_windows: dict[str, deque] = defaultdict(deque)   # ❌ RAM của 1 tiến trình
_daily_cost = 0.0                                       # ❌ nt
```

Checklist yêu cầu *"Stateless design (Redis)"*. Đã chuyển cả hai sang Redis, giữ chế độ RAM làm phương án dự phòng khi không có `REDIS_URL` (để chạy local vẫn được).

**Kiểm chứng bằng con số** — cấu hình `RATE_LIMIT_PER_MINUTE=10`, chạy 3 instance:

```
  req  1 -> 200      req  6 -> 200      req 11 -> 429
  req  2 -> 200      req  7 -> 200      req 12 -> 429
  req  3 -> 200      req  8 -> 200      req 13 -> 429
  req  4 -> 200      req  9 -> 200      req 14 -> 429
  req  5 -> 200      req 10 -> 200      req 15 -> 429

  TỔNG: đúng 10 x 200, 5 x 429
```

Nếu vẫn đếm trong RAM, mỗi instance sẽ có sổ riêng cho 10 request → phải tới **request thứ 30** mới bị chặn. Con số **10** chính là bằng chứng cả 3 instance đang dùng chung một bộ đếm.

**Phép thử khắc nghiệt hơn — giết instance giữa chừng:**

```
  req 1..5  -> 200          (dùng 5/10)
  >> docker stop 06-lab-complete-agent-1 <<
  req 6..10 -> 200          (đếm tiếp 6,7,8,9,10 — KHÔNG reset về 0)
  req 11,12 -> 429
```

Bộ đếm **tiếp tục từ 5** chứ không quay về 0, dù một instance đã chết hẳn. Nếu state nằm trong RAM thì giết instance là mất sạch, kẻ tấn công chỉ cần chờ deploy là được reset quota.

### Load balancing

```
  req 1 -> 172.18.0.5:8000      req 4 -> 172.18.0.5:8000      req 7 -> 172.18.0.5:8000
  req 2 -> 172.18.0.3:8000      req 5 -> 172.18.0.3:8000      req 8 -> 172.18.0.3:8000
  req 3 -> 172.18.0.4:8000      req 6 -> 172.18.0.4:8000      req 9 -> 172.18.0.4:8000
```

Round-robin đều tuyệt đối qua 3 instance.

### Kết quả test toàn bộ

| Nhóm | Kiểm tra | Kết quả |
|---|---|---|
| Public | `GET /` | 200 |
| Public | `GET /health` | 200, `uptime=22.7s` |
| Public | `GET /ready` | 200, `storage=redis` |
| Auth | Không có key | **401** `Missing API key` |
| Auth | Key sai | **403** `Invalid API key` |
| Auth | Key đúng | 200 + `usage` |
| Validation | `question` rỗng | **422** (`min_length=1`) |
| Validation | `question` 2500 ký tự | **422** (`max_length=2000`) |
| Rate limit | 15 request liên tiếp | 10 x 200, 5 x **429** |
| Bảo vệ | `/metrics` không key | **401** |
| Bảo vệ | `/metrics` có key | 200 + số liệu chi tiêu |
| Headers | `X-Frame-Options` | `DENY` |
| Headers | `X-Content-Type-Options` | `nosniff` |
| Headers | `X-XSS-Protection` | `1; mode=block` |

Response mẫu của `/ask`:

```json
{
  "question": "Hello",
  "answer": "Đây là câu trả lời từ AI agent (mock)...",
  "model": "gpt-4o-mini",
  "timestamp": "2026-08-10T04:01:33+00:00",
  "usage": {
    "requests_remaining": 9,
    "budget_used_usd": 2.1e-05,
    "budget_remaining_usd": 4.999979
  }
}
```

### 4 bug đã phát hiện và sửa trong `06-lab-complete`

#### Bug 1 — Container crash loop: `No module named 'uvicorn'`

Triệu chứng: cả 3 agent `Restarting (1)` liên tục.

```
ModuleNotFoundError: No module named 'uvicorn'
```

Lạ ở chỗ file `/home/agent/.local/bin/uvicorn` **có tồn tại**, chỉ là nó không import được thư viện.

Nguyên nhân: Dockerfile tạo user bằng `useradd -r -g agent -d /app agent`, tức `HOME=/app`. Python tự động thêm `$HOME/.local/lib/python3.11/site-packages` vào `sys.path` — nghĩa là nó tìm ở `/app/.local/...`, trong khi packages được copy sang `/home/agent/.local/...`. Hai đường dẫn lệch nhau.

**Đã sửa** — thêm vào Dockerfile:

```dockerfile
ENV PYTHONUSERBASE=/home/agent/.local
```

Dockerfile của Part 5 có sẵn dòng này nên chạy được; Part 6 bị bỏ sót.

#### Bug 2 — Mọi request đều trả 500

```
AttributeError: 'MutableHeaders' object has no attribute 'pop'
  File "/app/app/main.py", line 129, in request_middleware
    response.headers.pop("server", None)
```

`response.headers` là `MutableHeaders` của Starlette — nó kế thừa `Mapping` (chỉ đọc) chứ không phải `MutableMapping`, nên **không có** method `.pop()`.

Middleware chạy cho **mọi** request, nên bug này làm toàn bộ API chết, kể cả `/health`.

**Đã sửa:**

```python
if "server" in response.headers:
    del response.headers["server"]
```

#### Bug 3 — "Graceful shutdown" lại phá chính graceful shutdown

Đây là bug tinh vi nhất của cả lab. Code gốc:

```python
def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))   # chỉ ghi log

signal.signal(signal.SIGTERM, _handle_signal)
```

Hàm này **ghi đè** handler SIGTERM của uvicorn nhưng không làm gì tiếp. Hậu quả ngược hoàn toàn với ý định: app nhận SIGTERM, ghi log, rồi **chạy tiếp như chưa có gì xảy ra**. Docker chờ hết 10 giây rồi buộc phải SIGKILL — đúng thứ mà graceful shutdown sinh ra để tránh.

**Đo thực tế trước khi sửa:**

```bash
$ time docker stop 06-lab-complete-agent-2
real    0m10.367s          ← chờ hết timeout rồi bị giết cứng
```

**Đã sửa** — lưu handler cũ rồi gọi lại sau khi ghi log:

```python
def _handle_signal(signum, frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))
    if callable(_previous_sigterm):
        _previous_sigterm(signum, frame)          # trả quyền cho uvicorn
    else:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGTERM)

_previous_sigterm = signal.getsignal(signal.SIGTERM)
signal.signal(signal.SIGTERM, _handle_signal)
```

**Đo lại sau khi sửa:**

```bash
$ time docker stop 06-lab-complete-agent-3
real    0m0.768s           ← tự thoát sạch

# log xác nhận lifespan shutdown đã chạy:
{"ts":"...","lvl":"INFO","msg":"{"event": "shutdown", "served": 0}"}
INFO:     Application shutdown complete.
```

**10,4 giây → 0,77 giây.** Bài học: đăng ký signal handler mà không gọi tiếp handler cũ là **vô hiệu hoá** hành vi mặc định, chứ không phải bổ sung thêm vào nó.

#### Bug 4 — `check_production_ready.py` crash trên Windows

```
UnicodeDecodeError: 'charmap' codec can't decode byte 0x8d in position 639
```

Script gọi `open(path).read()` không chỉ định encoding. Trên Windows, `open()` mặc định dùng encoding hệ thống (cp1252), gặp tiếng Việt hoặc emoji trong chính source của lab là chết ngay. Trên Linux/macOS mặc định là UTF-8 nên không lộ ra.

**Đã sửa** — gom thành một hàm dùng chung và thay cả 5 chỗ gọi:

```python
def read_text(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()
```

### 2 tối ưu ngoài yêu cầu

**1. Bỏ `gcc` khỏi Dockerfile.** Giống Part 5 — không dependency nào cần biên dịch, khối `apt-get install gcc libpq-dev` chỉ tốn thêm ~200 MB tải và vài phút build.

**2. So sánh API key bằng `hmac.compare_digest`.**

```python
for valid in _valid_keys():
    if hmac.compare_digest(api_key, valid):
        return api_key
```

Toán tử `==` thoát ra ngay khi gặp ký tự khác nhau đầu tiên, nên thời gian phản hồi tiết lộ *khớp được bao nhiêu ký tự đầu*. Kẻ tấn công đo đủ nhiều lần có thể dò ra key từng ký tự một (timing attack). `hmac.compare_digest` luôn chạy hết chuỗi, thời gian không đổi.

Hàm `verify_api_key` cũng nhận **nhiều key** ngăn cách bởi dấu phẩy, để xoay key không cần downtime: thêm key mới → báo client đổi → gỡ key cũ.
