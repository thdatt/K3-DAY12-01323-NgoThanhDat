# Deployment Information

> **Student Name:** Ngô Thành Đạt
> **Student ID:** 01323
> **Repo:** K3-DAY12-01323-NgoThanhDat

---

## Public URL

```
https://day12-agent-production-5236.up.railway.app
```

Thử nhanh: [/health](https://day12-agent-production-5236.up.railway.app/health) · [/ready](https://day12-agent-production-5236.up.railway.app/ready)

## Platform

**Railway** — gói Trial. `LOCAL_FALLBACK=false` (deploy cloud thật, không dùng phương án dự phòng local).

| | |
|---|---|
| Project | `day12-agent-ngothanhdat` |
| Project ID | `3c6553f1-ceaa-4b49-8ad6-6f29dd32fa4d` |
| Service app | `day12-agent` — ● Online |
| Service DB | `Redis` — ● Online (volume 500 MB) |
| Region | `sfo` (US West) |
| Builder | Dockerfile (multi-stage) |
| Deploy từ | Thư mục **gốc** repo |

## API Key dùng để chấm

```
hFXUe3b2ohxnbgQ8m1pahBiPXVCH6Z_q
```

> Key sinh ngẫu nhiên riêng cho bài tập. Agent dùng mock LLM nên không phát sinh chi phí thật.
> Đổi key: `railway variables --set "AGENT_API_KEY=<key-moi>" --service day12-agent`

---

## ✅ Required Evidence (CP5)

Chạy lúc 10/08/2026 trên URL công khai. Kết quả thật, không cắt ghép.

| # | Kiểm tra | Kỳ vọng | Kết quả |
|---|---|---|---|
| 1 | `GET /health` | 200 | ✅ **200** |
| 2 | `GET /ready` | 200 | ✅ **200** |
| 3 | `POST /ask` không truyền API key | 401 Unauthorized | ✅ **401** |
| 4 | `POST /ask` truyền đúng API key | 200 OK | ✅ **200** |

### 1. `GET /health` → 200

```json
{"status":"ok","uptime_seconds":289.5,"in_flight":1,"shutting_down":false}
```

### 2. `GET /ready` → 200

```json
{"ready":true,"redis":"connected"}
```

`"redis":"connected"` là bằng chứng quan trọng nhất: agent trên cloud đang dùng Redis add-on của Railway để lưu rate limit, ngân sách và lịch sử hội thoại. Nếu ra `503 redis_unavailable` nghĩa là biến `REDIS_URL` chưa được nối.

### 3. `POST /ask` không truyền API key → 401

```json
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

Truyền sai key cũng trả **401** (`{"detail":"Invalid API key."}`) — đúng đặc tả CP3: *"Sai hoặc thiếu → 401 Unauthorized"*.

### 4. `POST /ask` truyền đúng API key → 200

```json
{
  "answer": "Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!",
  "user_id": "sv01",
  "history_length": 2,
  "message_count": 4,
  "usage": {
    "input_tokens": 42,
    "output_tokens": 30,
    "cost_usd": 2.43e-05,
    "month_total_usd": 4.3e-05,
    "budget_usd": 10.0,
    "requests_remaining": 9
  }
}
```

---

## Environment Variables trên Railway

| Biến | Nguồn | Ghi chú |
|---|---|---|
| `PORT` | Railway tự inject | **Không đặt tay** — đặt tay sẽ khiến app nghe sai cổng |
| `REDIS_URL` | Railway tự inject | Có sau `railway add --database redis` |
| `AGENT_API_KEY` | Đặt tay | Secret — không commit |
| `RATE_LIMIT_PER_MINUTE` | Đặt tay | `10` |
| `MONTHLY_BUDGET_USD` | Đặt tay | `10.0` |
| `LOG_LEVEL` | Đặt tay | `INFO` |

---

## Các bước deploy (tái lập được)

```bash
npm i -g @railway/cli
railway login                       # mở trình duyệt

railway init -n day12-agent-ngothanhdat
railway add --database redis        # tạo Redis, Railway tự sinh REDIS_URL
railway add --service day12-agent   # tạo service app — CLI chuyển link sang đây
railway status                      # XÁC NHẬN đang link đúng service trước khi up

railway variables --set "AGENT_API_KEY=$(python -c 'import secrets;print(secrets.token_urlsafe(24))')" \
                  --set "RATE_LIMIT_PER_MINUTE=10" \
                  --set "MONTHLY_BUDGET_USD=10.0" \
                  --service day12-agent

railway up --detach --service day12-agent
railway domain --service day12-agent
```

---

## ⚠️ 3 vấn đề gặp khi deploy thật và cách xử lý

### 1. `railway.toml` khiến deploy chết ngay

```
Error: Invalid value for '--port': '$PORT' is not a valid integer.
```

Railway chạy `startCommand` ở dạng **exec** (không qua shell) nên chuỗi `$PORT` được truyền nguyên văn cho uvicorn thay vì thay bằng số cổng.

**Sửa** — bọc trong `sh -c` để shell làm việc thay biến:

```toml
startCommand = "sh -c 'exec uvicorn app.main:app --host 0.0.0.0 --port $PORT'"
```

Từ khoá `exec` cũng quan trọng: nó khiến uvicorn thay thế tiến trình `sh` và trở thành PID 1, nhận trực tiếp SIGTERM. Thiếu `exec` thì `sh` giữ PID 1, không chuyển tín hiệu xuống, graceful shutdown không bao giờ chạy.

> Render **không** cần bọc `sh -c` vì Render chạy start command qua shell. Đây là khác biệt thật giữa 2 nền tảng.

### 2. `railway up` deploy nhầm vào service Redis

Sau `railway add --database redis`, CLI **tự động link vào service Redis vừa tạo**. Gọi `railway up` ngay sau đó sẽ đẩy code app đè lên Redis.

**Phòng tránh:** tạo service app rồi mới `up`, và luôn ghi rõ `--service <tên-app>`. Chạy `railway status` để xác nhận trước.

**Khắc phục nếu lỡ:** deployment sai sẽ FAILED nhưng `source.image` của Redis vẫn nguyên. Khôi phục bằng:

```bash
railway redeploy --service Redis --from-source --yes
```

### 3. Đặt biến môi trường xong phải deploy lại

`railway variables --set` chỉ ghi biến vào cấu hình; container đang chạy không tự nạp. Phải `railway redeploy --service <app> --yes`.

---

## Screenshots

| Ảnh | Nội dung | Chứng minh |
|---|---|---|
| [dashboard.png](screenshots/dashboard.png) | Dashboard Railway | 2 service `day12-agent` + `Redis` đều **Online** |
| [running.png](screenshots/running.png) | Tab Deployments | **ACTIVE** · *Deployment successful* · domain · region |
| [health.png](screenshots/health.png) | Trình duyệt mở `/health` | Dịch vụ chạy thật trên internet |
| [test.png](screenshots/test.png) | Terminal — 5 mục kiểm thử | `200 · 200 · 401 · 403 · 200` |
| [ratelimit.png](screenshots/ratelimit.png) | Terminal — 15 request | Đúng 10 lần 200 rồi 5 lần 429 |
| [variables.png](screenshots/variables.png) | Tab Variables | Secret đã che `*******` |

> **Về bảo mật ảnh chụp:** lần chụp đầu, `REDIS_URL` hiện nguyên văn mật khẩu Redis. Railway để biến này hiện mặc định, khác với `AGENT_API_KEY` và `JWT_SECRET` vốn ẩn sẵn — rất dễ sơ suất. Đã chụp lại sau khi bấm ẩn.

---

## Kiểm tra ở local (`docker compose`)

```
$ docker compose up -d --scale agent=3
$ docker compose ps

k3-day12-01323-ngothanhdat-agent-1 | Up (healthy)
k3-day12-01323-ngothanhdat-agent-2 | Up (healthy)
k3-day12-01323-ngothanhdat-agent-3 | Up (healthy)
k3-day12-01323-ngothanhdat-nginx-1 | Up
k3-day12-01323-ngothanhdat-redis-1 | Up (healthy)

$ docker images day12-agent:prod
241MB          (yêu cầu ≤ 500MB)

$ docker exec <agent> whoami
appuser        (non-root)
```

**Test stateless qua Nginx cổng 8000** — 5 request cùng `X-User-Id`:

```
lần 1 -> instance 172.19.0.3:8000  history_length = 1
lần 2 -> instance 172.19.0.4:8000  history_length = 2
lần 3 -> instance 172.19.0.5:8000  history_length = 3
lần 4 -> instance 172.19.0.3:8000  history_length = 4
lần 5 -> instance 172.19.0.4:8000  history_length = 5
```

**Test graceful shutdown:**

```
$ time docker stop k3-day12-01323-ngothanhdat-agent-1
real    0m0.515s          ← tự thoát, không bị SIGKILL sau 10s
```

Chi tiết phân tích nằm ở [exercises.md](exercises.md).
