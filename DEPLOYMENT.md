# Deployment Information

> **Student Name:** Ngô Thành Đạt
> **Student ID:** 2A202601323

---

## ✅ Trạng thái: ĐANG CHẠY

Deploy thành công lên Railway ngày 10/08/2026. Tất cả test đều pass — kết quả thật ở phần dưới.

---

## Public URL

```
https://day12-agent-production-5236.up.railway.app
```

Thử nhanh: [/health](https://day12-agent-production-5236.up.railway.app/health)

## Platform

**Railway** — gói Trial

| | |
|---|---|
| Project | `day12-agent-ngothanhdat` |
| Project ID | `3c6553f1-ceaa-4b49-8ad6-6f29dd32fa4d` |
| Service app | `day12-agent` — ● Online |
| Service DB | `Redis` — ● Online (volume 500 MB) |
| Region | `sfo` |
| Builder | Dockerfile (multi-stage) |

## Thư mục deploy

`06-lab-complete/`

## API Key

```
7WnZAOeQZ22fmWshPRa-hTI3HDDwi0tT
```

> Key này sinh ngẫu nhiên riêng cho bài tập, dùng mock LLM nên không tốn tiền thật.
> Muốn đổi: `railway variables --set "AGENT_API_KEY=<key-moi>" --service day12-agent`

---

## Các bước deploy lên Railway

### Bước 1 — Cài Railway CLI

```bash
npm i -g @railway/cli
railway --version
```

### Bước 2 — Đăng nhập

```bash
railway login
```

Lệnh này mở trình duyệt. Đăng nhập bằng GitHub cho nhanh.

### Bước 3 — Khởi tạo project

```bash
cd 06-lab-complete
railway init
```

Đặt tên project, ví dụ `day12-agent-ngothanhdat`.

### Bước 4 — Thêm Redis

```bash
railway add --database redis
```

Railway sẽ tự tạo biến `REDIS_URL` và tiêm vào service. **Không cần** đặt tay biến này.

> Thiếu bước này, agent vẫn chạy nhưng rơi về chế độ đếm trong RAM — rate limit và budget sẽ sai khi Railway scale lên nhiều instance.

### Bước 5 — Đặt biến môi trường

```bash
railway variables --set "AGENT_API_KEY=<sinh-mot-chuoi-ngau-nhien>"
railway variables --set "JWT_SECRET=<sinh-mot-chuoi-khac>"
railway variables --set "ENVIRONMENT=production"
railway variables --set "RATE_LIMIT_PER_MINUTE=10"
railway variables --set "DAILY_BUDGET_USD=5.0"
railway variables --set "GLOBAL_DAILY_BUDGET_USD=50.0"
```

Sinh chuỗi ngẫu nhiên an toàn:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**⚠️ Hai lưu ý quan trọng:**

1. **Đừng đặt biến `PORT`.** Railway tự tiêm giá trị này. Đặt tay sẽ khiến app nghe sai cổng → health check fail → deploy hỏng. *(`CODE_LAB.md` bước 4 hướng dẫn `railway variables set PORT=8000` — đừng làm theo.)*

2. **Cú pháp `railway variables set KEY=value` đã lỗi thời.** CLI bản mới dùng `railway variables --set "KEY=value"`.

3. `ENVIRONMENT=production` bắt buộc phải đi kèm `AGENT_API_KEY` và `JWT_SECRET` thật — nếu để giá trị mặc định, `config.py` sẽ **cố tình crash** ngay lúc khởi động (fail fast), chống việc vô tình chạy production với key demo.

### Bước 6 — Deploy

```bash
railway up
```

### Bước 7 — Lấy URL công khai

```bash
railway domain
```

### Bước 8 — Xem log nếu có lỗi

```bash
railway logs
```

---

## Environment Variables đã đặt

| Biến | Nguồn | Ghi chú |
|---|---|---|
| `PORT` | Railway tự tiêm | **Không đặt tay** |
| `REDIS_URL` | Railway tự tiêm | Có sau khi `railway add --database redis` |
| `AGENT_API_KEY` | Đặt tay | Secret — không commit |
| `JWT_SECRET` | Đặt tay | Secret — không commit |
| `ENVIRONMENT` | Đặt tay | `production` |
| `RATE_LIMIT_PER_MINUTE` | Đặt tay | `10` |
| `DAILY_BUDGET_USD` | Đặt tay | `5.0` |
| `GLOBAL_DAILY_BUDGET_USD` | Đặt tay | `50.0` |

---

## 🧪 KẾT QUẢ TEST THẬT TRÊN CLOUD

Chạy lúc 10/08/2026, trên URL công khai `https://day12-agent-production-5236.up.railway.app`.

### Tổng kết: 12/12 mục pass

| # | Kiểm tra | HTTP | Kết quả |
|---|---|---|---|
| 1 | `GET /health` | **200** | `environment: production` |
| 2 | `GET /ready` | **200** | `storage: redis` ✅ |
| 3 | `POST /ask` không key | **401** | `Missing API key` |
| 4 | `POST /ask` key sai | **403** | `Invalid API key` |
| 5 | `POST /ask` key đúng | **200** | Trả lời + usage |
| 6 | Rate limit 15 request | 9x200 + 6x**429** | Chặn đúng ngưỡng |
| 7 | `question` rỗng | **422** | Pydantic chặn |
| 8 | `question` 2500 ký tự | **422** | Pydantic chặn |
| 9 | `GET /metrics` không key | **401** | Có bảo vệ |
| 10 | `GET /metrics` có key | **200** | `storage: redis` |
| 11 | Security headers | — | `X-Frame-Options: DENY`, `nosniff` |
| 12 | `GET /docs` | **404** | Đã tắt trong production ✅ |

### Chi tiết

**1. Health check**

```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "production",
  "uptime_seconds": 88.1,
  "total_requests": 1,
  "checks": {"llm": "mock"},
  "timestamp": "2026-08-10T04:32:20.814212+00:00"
}
```

**2. Readiness — bằng chứng đã nối được Redis trên cloud**

```json
{"ready": true, "storage": "redis"}
```

`"storage": "redis"` là mục quan trọng nhất. Nó chứng minh agent trên cloud đang lưu bộ đếm rate limit và chi phí trong Redis dùng chung, chứ không phải trong RAM. Nếu ra `"memory"` là biến `REDIS_URL` chưa được nối.

**3–5. Xác thực**

```
Không key -> 401  {"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
Key sai   -> 403  {"detail":"Invalid API key."}
Key đúng  -> 200
```

```json
{
  "question": "What is Docker?",
  "answer": "Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!",
  "model": "gpt-4o-mini",
  "timestamp": "2026-08-10T04:32:22.929389+00:00",
  "usage": {
    "requests_remaining": 9,
    "budget_used_usd": 1.9e-05,
    "budget_remaining_usd": 4.999981
  }
}
```

**6. Rate limiting — `RATE_LIMIT_PER_MINUTE=10`**

```
req  1 -> 200      req  6 -> 200      req 11 -> 429
req  2 -> 200      req  7 -> 200      req 12 -> 429
req  3 -> 200      req  8 -> 200      req 13 -> 429
req  4 -> 200      req  9 -> 200      req 14 -> 429
req  5 -> 200      req 10 -> 429      req 15 -> 429
```

9 lần thành công vì request ở mục 5 đã tiêu 1 slot trước đó — tổng đúng **10**, khớp cấu hình.

**8. Metrics**

```json
{
  "uptime_seconds": 118.3,
  "total_requests": 9,
  "error_count": 0,
  "rate_limit_per_minute": 10,
  "date": "2026-08-10",
  "used_usd": 0.000179,
  "budget_usd": 5.0,
  "remaining_usd": 4.999821,
  "global_used_usd": 0.000179,
  "global_budget_usd": 50.0,
  "storage": "redis"
}
```

**9. Security headers**

```
Server: railway-hikari
x-content-type-options: nosniff
x-frame-options: DENY
```

**10. `/docs` đã tắt**

```
GET /docs -> 404
```

`main.py` đặt `docs_url=None` khi `ENVIRONMENT=production`. Sơ đồ API công khai giúp kẻ tấn công dò endpoint dễ hơn nhiều, nên production phải tắt.

---

## ⚠️ 3 vấn đề gặp khi deploy thật và cách xử lý

### Vấn đề 1 — `railway.toml` làm deploy chết ngay

Log lỗi:

```
Error: Invalid value for '--port': '$PORT' is not a valid integer.
```

File gốc viết:

```toml
startCommand = "uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2"
```

Railway chạy `startCommand` ở dạng **exec**, tức là không qua shell. Nên chuỗi `$PORT` được truyền **nguyên văn** cho uvicorn thay vì bị thay bằng số cổng thật.

**Đã sửa** — bọc trong `sh -c` để shell thay biến trước:

```toml
startCommand = "sh -c 'uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2'"
```

> Lỗi này cũng có trong `03-cloud-deployment/railway/railway.toml`, ai deploy thư mục đó sẽ gặp y hệt.

### Vấn đề 2 — `railway up` deploy nhầm vào service Redis

Chạy `railway init` rồi `railway add --database redis` thì CLI **tự link vào service Redis vừa tạo**. Gọi `railway up` ngay sau đó sẽ đẩy code app đè lên Redis.

**Thứ tự đúng:**

```bash
railway init -n <ten-project>
railway add --database redis      # tạo Redis (CLI link vào Redis)
railway add --service <ten-app>   # tạo service app (CLI chuyển link sang app)
railway up --service <ten-app>    # ghi rõ --service cho chắc
```

Luôn chạy `railway status` trước khi `railway up` để xác nhận đang link đúng service.

**Nếu lỡ deploy nhầm:** deployment sai sẽ FAILED nhưng `source.image` của Redis vẫn nguyên. Khôi phục bằng:

```bash
railway redeploy --service Redis --from-source --yes
```

Cờ `--from-source` bảo Railway deploy lại từ **image gốc** đã cấu hình, thay vì lặp lại deployment lỗi.

### Vấn đề 3 — Đặt biến môi trường xong phải deploy lại

`railway variables --set` chỉ ghi biến, container đang chạy **không tự nạp**. Phải:

```bash
railway redeploy --service <ten-app> --yes
```

---

## Test Commands

Thay `<URL>` = `https://day12-agent-production-5236.up.railway.app` và `<KEY>` = `7WnZAOeQZ22fmWshPRa-hTI3HDDwi0tT`.

### 1. Health check — không cần key

```bash
curl <URL>/health
```

Kết quả mong đợi:

```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "production",
  "uptime_seconds": 42.1,
  "total_requests": 7,
  "checks": {"llm": "mock"},
  "timestamp": "2026-08-10T04:00:00+00:00"
}
```

### 2. Readiness check — xác nhận đã nối được Redis

```bash
curl <URL>/ready
```

```json
{"ready": true, "storage": "redis"}
```

`"storage": "memory"` nghĩa là **chưa nối được Redis** — kiểm tra lại bước 4.

### 3. Không có API key → 401

```bash
curl -i -X POST <URL>/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Hello"}'
```

```
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

### 4. Sai API key → 403

```bash
curl -i -X POST <URL>/ask \
  -H "X-API-Key: sai-key" \
  -H "Content-Type: application/json" \
  -d '{"question":"Hello"}'
```

```
HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}
```

### 5. Đúng API key → 200

```bash
curl -X POST <URL>/ask \
  -H "X-API-Key: <KEY>" \
  -H "Content-Type: application/json" \
  -d '{"question":"What is Docker?"}'
```

```json
{
  "question": "What is Docker?",
  "answer": "Container là cách đóng gói app để chạy ở mọi nơi...",
  "model": "gpt-4o-mini",
  "timestamp": "2026-08-10T04:00:00+00:00",
  "usage": {
    "requests_remaining": 9,
    "budget_used_usd": 2.1e-05,
    "budget_remaining_usd": 4.999979
  }
}
```

### 6. Rate limiting → 429 sau 10 request

```bash
for i in $(seq 1 15); do
  printf "req %2d -> " "$i"
  curl -s -o /dev/null -w "%{http_code}\n" -X POST <URL>/ask \
    -H "X-API-Key: <KEY>" \
    -H "Content-Type: application/json" \
    -d '{"question":"test"}'
done
```

Kết quả mong đợi: 10 lần `200`, rồi 5 lần `429`.

### 7. Kiểm tra đầu vào → 422

```bash
# Rỗng
curl -s -o /dev/null -w "%{http_code}\n" -X POST <URL>/ask \
  -H "X-API-Key: <KEY>" -H "Content-Type: application/json" \
  -d '{"question":""}'

# Quá dài (>2000 ký tự)
curl -s -o /dev/null -w "%{http_code}\n" -X POST <URL>/ask \
  -H "X-API-Key: <KEY>" -H "Content-Type: application/json" \
  -d "{\"question\":\"$(python -c 'print("x"*2500)')\"}"
```

Cả hai đều trả `422`.

### 8. Metrics — có bảo vệ

```bash
curl <URL>/metrics -H "X-API-Key: <KEY>"
```

```json
{
  "uptime_seconds": 120.5,
  "total_requests": 35,
  "error_count": 0,
  "rate_limit_per_minute": 10,
  "used_usd": 0.000193,
  "budget_usd": 5.0,
  "remaining_usd": 4.999807,
  "storage": "redis"
}
```

### 9. Security headers

```bash
curl -I <URL>/health
```

Phải thấy `X-Frame-Options: DENY` và `X-Content-Type-Options: nosniff`.

---

## Screenshots

Đủ 6 ảnh trong thư mục [`screenshots/`](screenshots/):

| Ảnh | Nội dung | Chứng minh điều gì |
|---|---|---|
| [dashboard.png](screenshots/dashboard.png) | Dashboard Railway | 2 service `day12-agent` và `Redis` đều **Online**, có `redis-volume` |
| [running.png](screenshots/running.png) | Tab Deployments | **ACTIVE** · *Deployment successful* · domain · region `US West` · 1 Replica |
| [health.png](screenshots/health.png) | Trình duyệt mở `/health` | Dịch vụ chạy thật trên internet, `environment: production` |
| [test.png](screenshots/test.png) | Terminal — 5 mục kiểm thử | `200 · 200 · 401 · 403 · 200`, đều khớp kỳ vọng |
| [ratelimit.png](screenshots/ratelimit.png) | Terminal — 15 request | Đúng **10 lần 200** rồi **5 lần 429** |
| [variables.png](screenshots/variables.png) | Tab Variables | 7 biến; `AGENT_API_KEY`, `JWT_SECRET`, `REDIS_URL` đã che `*******` |

Ảnh `test.png` và `ratelimit.png` được tạo bằng script [`screenshots/chup_anh.ps1`](screenshots/chup_anh.ps1) — chạy lại lúc nào cũng cho kết quả tương tự:

```powershell
.\screenshots\chup_anh.ps1
```

Script tự chờ 65 giây cho bộ đếm rate limit reset trước mỗi phần, nên kết quả luôn sạch.

> **Về bảo mật ảnh chụp:** ảnh `variables.png` đã được kiểm tra kỹ trước khi commit. Lần chụp đầu tiên `REDIS_URL` hiện nguyên văn mật khẩu Redis (`redis://default:<password>@redis.railway.internal:6379`) — đã chụp lại sau khi bấm ẩn. Đây là chỗ rất dễ sơ suất: Railway để `REDIS_URL` hiện mặc định, khác với `AGENT_API_KEY` và `JWT_SECRET` vốn đã ẩn sẵn.

---

## Kết quả kiểm tra ở local

Trước khi deploy, toàn bộ stack đã chạy và test thành công tại máy:

```
$ python check_production_ready.py
  Result: 20/20 checks passed (100%)
  🎉 PRODUCTION READY!

$ docker compose up -d --build --scale agent=3
06-lab-complete-agent-1 | Up (healthy)
06-lab-complete-agent-2 | Up (healthy)
06-lab-complete-agent-3 | Up (healthy)
06-lab-complete-nginx-1 | Up
06-lab-complete-redis-1 | Up (healthy)

Image size: 248 MB  (yêu cầu < 500 MB)
```

Chi tiết kết quả test nằm ở [MISSION_ANSWERS.md](MISSION_ANSWERS.md) phần Part 6.
