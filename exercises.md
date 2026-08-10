# Exercises — Lab 12: Cloud Services & Deployment

> **Student Name:** Ngô Thành Đạt
> **Student ID:** 01323
> **Repo:** K3-DAY12-01323-NgoThanhDat
> **Ngày làm:** 10/08/2026

> ⚠️ **Lưu ý:** 7 câu dưới đây lấy đúng từ mục *"Tự kiểm · Giải thích"* của các checkpoint CP0–CP5 trong codelab. Nếu file `exercises.md` trong starter repo có bộ 10 câu khác, hãy đối chiếu và bổ sung — nội dung trả lời bên dưới đều dựa trên quan sát thực tế khi chạy code nên vẫn dùng lại được.

---

## Câu 1 — Tại sao cần **cả** rate limit **và** cost guard?

Vì chúng chặn hai loại lạm dụng khác nhau, và cái này không thay được cái kia.

**Rate limit bảo vệ hạ tầng** — chặn user gửi request quá nhanh. Đơn vị đo là *số request / phút*. Không có nó, một vòng lặp lỗi phía client có thể bắn hàng nghìn request/giây làm sập server.

**Cost guard bảo vệ ngân sách** — chặn user tiêu quá nhiều tiền. Đơn vị đo là *USD / tháng*. LLM tính tiền theo token, mà số token mỗi request lại rất khác nhau.

**Tình huống rate limit cho qua nhưng cost guard phải chặn:** user gửi đúng 1 request/phút — hoàn toàn không vi phạm tốc độ — nhưng mỗi request đính kèm một file 100 trang để tóm tắt. Mỗi lần gọi tốn cỡ 50.000 token. Sau 200 request (hơn 3 tiếng, rất "lịch sự" về tốc độ) là đã đốt hết ngân sách tháng. Rate limit hoàn toàn mù trước kiểu tấn công này vì nó chỉ đếm *số lần*, không đếm *khối lượng*.

**Tình huống ngược lại — cost guard cho qua nhưng rate limit phải chặn:** user bắn 500 request/giây, mỗi request chỉ 1 chữ "hi". Tổng chi phí gần như bằng 0 nên cost guard thấy vẫn còn thừa ngân sách, nhưng server sập vì không kịp xử lý số kết nối đó.

Kiểm chứng trong code: `app/main.py` gọi `limiter.check()` **trước** rồi mới `guard.check()`. Cả hai đều chạy **trước** `ask_llm()` — vì bước gọi LLM mới là bước tốn tiền, phải chặn trước khi tới đó.

---

## Câu 2 — Tại sao lưu state trong dict Python lại gây lỗi khi chạy 3 container?

Vì mỗi container là một **tiến trình riêng, có vùng nhớ riêng**. Dict Python nằm trong RAM của đúng một tiến trình, hai tiến trình còn lại không nhìn thấy gì.

Load balancer chia request theo vòng tròn, nên:

```
Request 1  ──> Container A   (lưu vào RAM của A)
Request 2  ──> Container B   (RAM của B trống → "bạn là ai?")
Request 3  ──> Container C   (RAM của C trống → quên tiếp)
Request 4  ──> Container A   (nhớ lại được request 1, nhưng mất 2 và 3)
```

Người dùng thấy agent **mất trí nhớ ngẫu nhiên** — lúc nhớ lúc quên tuỳ request rơi vào container nào.

Điều nguy hiểm nhất: chạy 1 container ở máy local thì **không bao giờ tái hiện được lỗi này**. Code chạy hoàn hảo trên máy dev, lên production mới hỏng.

Với rate limit thì hậu quả còn tệ hơn — không chỉ sai mà còn *thủng bảo mật*: giới hạn 10 req/phút chia cho 3 container thành 30 req/phút thực tế.

Đã kiểm chứng ở Câu 6 bên dưới.

---

## Câu 3 (CP1) — Fail-fast khi thiếu `AGENT_API_KEY` cứu bạn thế nào?

**Tình huống cụ thể:** deploy bản mới lên Railway lúc 11 giờ đêm. Do vội, tôi quên đặt biến `AGENT_API_KEY` cho service.

**Nếu code để mặc định `"changeme"`:** deploy thành công, health check xanh, dashboard báo Active. Nhìn mọi thứ đều bình thường nên tôi đi ngủ. Nhưng API lúc này chấp nhận key `"changeme"` — chuỗi mà bất kỳ ai đọc source trên GitHub cũng đoán ra. Sáng hôm sau phát hiện hàng nghìn request lạ và hoá đơn LLM tăng vọt. Tệ hơn nữa là **không có dấu hiệu nào để phát hiện sớm**: log vẫn 200 OK, health check vẫn xanh.

**Với fail-fast:** container crash ngay lúc khởi động, Railway báo deploy failed, tôi thấy lỗi trong 30 giây và sửa xong trước khi đi ngủ.

Cụ thể trong `app/config.py`, `agent_api_key: str` **không có giá trị mặc định** nên Pydantic raise ngay:

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
agent_api_key
  Field required [type=missing, input_value={}, input_type=dict]
```

Và hàm `_validate()` chặn thêm cả trường hợp key có giá trị nhưng là placeholder:

```
ValueError: AGENT_API_KEY chưa được cấu hình (đang để trống hoặc còn là
placeholder). Đặt biến môi trường AGENT_API_KEY bằng một chuỗi ngẫu nhiên
trước khi chạy app.
```

**Nguyên tắc rút ra:** lỗi cấu hình nên xuất hiện **lúc khởi động**, không phải lúc phục vụ request. Hỏng sớm và ồn ào thì rẻ; hỏng muộn và im lặng thì đắt.

---

## Câu 4 (CP2) — Nếu đặt `COPY . .` trước `RUN pip install` thì chuyện gì xảy ra?

**Mỗi lần sửa một dòng code, `pip install` sẽ chạy lại từ đầu.**

Docker build theo từng layer và cache theo thứ tự. Nguyên tắc: **một layer đổi thì mọi layer sau nó đều mất cache**.

Thứ tự sai:

```dockerfile
COPY . .                                   # layer A — đổi mỗi lần sửa code
RUN pip install -r requirements.txt        # layer B — mất cache theo A
```

Sửa một dấu chấm phẩy trong `main.py` → layer A đổi → layer B build lại → tải lại toàn bộ thư viện qua mạng. Từ vài giây thành vài phút, lặp lại **mỗi lần build**.

Thứ tự đúng (đang dùng trong `Dockerfile`):

```dockerfile
COPY requirements.txt .                    # layer A — hiếm khi đổi
RUN pip install --prefix=/install -r requirements.txt   # layer B — dùng cache
COPY app/ app/                             # layer C — đổi liên tục
COPY utils/ utils/
```

Sửa code chỉ build lại layer C. **Quan sát thực tế:** lần build đầu mất khoảng 40 giây; các lần sau khi chỉ sửa code trong `app/` thì `docker build` xong trong **3,4 giây** vì layer `pip install` được lấy từ cache.

**Nguyên tắc chung:** xếp lệnh Dockerfile theo tần suất thay đổi — thứ ít đổi nhất lên trên cùng.

---

## Câu 5 (CP2) — Multi-stage build tiết kiệm được gì? Non-root user giải quyết vấn đề gì?

**Multi-stage build.** Vấn đề: build 1 stage cho ra image 800 MB–1 GB vì chứa cả compiler, pip cache, build tools — những thứ chỉ cần lúc *build*, không cần lúc *chạy*.

Giải pháp là chia 2 stage: stage 1 cài mọi thứ vào `/install`, stage 2 bắt đầu từ image sạch và chỉ `COPY --from=builder /install /usr/local`. Toàn bộ stage 1 bị vứt bỏ.

**Kết quả đo được:** `docker images day12-agent:prod` → **241 MB**, đạt yêu cầu ≤ 500 MB.

Lợi ích không chỉ là dung lượng:

| | 1 stage | Multi-stage |
|---|---|---|
| Dung lượng | ~800 MB–1 GB | **241 MB** |
| Thời gian pull khi deploy | Chậm | Nhanh hơn 3–4 lần |
| Có compiler trong image | ✅ Có — rủi ro bảo mật | ❌ Không |

**Non-root user.** Container mặc định chạy bằng `root`. Nếu code có lỗ hổng (ví dụ path traversal, hoặc thư viện bị chèn mã độc) thì kẻ tấn công có quyền `root` **bên trong container**, từ đó có thể lợi dụng lỗ hổng kernel để leo thang ra máy host.

```dockerfile
RUN adduser --disabled-password --no-create-home appuser
USER appuser
```

Hai dòng này cắt đứt chuỗi tấn công: kẻ tấn công chỉ có quyền của `appuser`, không ghi được vào thư mục hệ thống, không cài được gói mới.

Kết hợp cả hai (không có compiler **và** không có quyền root) khiến container gần như vô dụng với kẻ tấn công: chiếm được cũng không biên dịch được mã độc, cũng không leo thang được quyền.

---

## Câu 6 (CP4) — Nếu lịch sử chat lưu trong dict Python, chạy `--scale agent=3` thì `history_length` thay đổi thế nào?

**Con số sẽ nhảy loạn xạ, không tăng đều.** Cụ thể với 5 request liên tiếp qua Nginx round-robin 3 container:

```
lần 1 → container A → history_length = 1     (A: 1 lượt)
lần 2 → container B → history_length = 1     (B mới toanh, không thấy gì của A)
lần 3 → container C → history_length = 1     (C cũng vậy)
lần 4 → container A → history_length = 2     (A nhớ lần 1 của chính nó)
lần 5 → container B → history_length = 2     (B nhớ lần 2 của chính nó)
```

Ra dãy **1, 1, 1, 2, 2** thay vì 1, 2, 3, 4, 5. Nguyên nhân đã giải thích ở Câu 2: mỗi container có vùng nhớ riêng, dict Python không được chia sẻ.

**Kết quả thực tế sau khi chuyển sang Redis** (`app/store.py`), chạy `docker compose up -d --scale agent=3` rồi gọi 5 lần cùng `X-User-Id: sv01` qua Nginx cổng 8000:

```
lần 1 -> instance 172.19.0.3:8000  history_length = 1
lần 2 -> instance 172.19.0.4:8000  history_length = 2
lần 3 -> instance 172.19.0.5:8000  history_length = 3
lần 4 -> instance 172.19.0.3:8000  history_length = 4
lần 5 -> instance 172.19.0.4:8000  history_length = 5
```

Ba địa chỉ IP khác nhau xuất hiện trong cột instance — chứng tỏ request thật sự rơi vào 3 container khác nhau — mà con số vẫn tăng đều **1, 2, 3, 4, 5**. Đó là bằng chứng thiết kế stateless hoạt động đúng.

Điểm mấu chốt: instance chỉ là **chỗ chạy code**, không phải **chỗ giữ dữ liệu**. Nhờ vậy muốn thêm, bớt hay restart instance lúc nào cũng được.

---

## Câu 7 (CP4) — Vì sao `/health` và `/ready` phải tách riêng, và hành xử khác nhau khi shutdown?

| | `/health` (Liveness) | `/ready` (Readiness) |
|---|---|---|
| Hỏi gì | "Tiến trình còn sống không?" | "Nhận request được chưa?" |
| Có gọi Redis không | **Không** | **Có** |
| Ai gọi | Platform / orchestrator | Load balancer |
| Fail thì sao | **Restart container** | **Ngừng đẩy traffic**, không restart |
| Khi nhận SIGTERM | Vẫn **200** đến khi tắt hẳn | **503 ngay lập tức** |

**Vì sao `/health` không được kiểm tra Redis?** Nếu có, Redis chỉ cần trục trặc 5 giây là platform tưởng **toàn bộ** container đã chết và restart đồng loạt. Một sự cố nhỏ ở tầng cache biến thành sập cả hệ thống — trong khi bản thân các container vẫn hoàn toàn khoẻ mạnh.

**Vì sao `/health` phải giữ 200 kể cả khi đang tắt dần?** Nếu trả 503 lúc này, orchestrator kết luận container đã chết và **giết tiến trình ngay lập tức**, trước khi các request đang chạy kịp hoàn thành. Như vậy là phá hỏng đúng thứ mà graceful shutdown sinh ra để bảo vệ.

**Vì sao `/ready` phải trả 503 ngay khi nhận SIGTERM?** Để load balancer lập tức ngừng gửi request mới vào, trong khi các request cũ vẫn được xử lý nốt. Không có bước này thì vừa chờ vừa nhận thêm việc mới, không bao giờ tắt xong.

**Kiểm chứng thực tế** — `docker stop` một container:

```
$ time docker stop k3-day12-01323-ngothanhdat-agent-1
real    0m0.515s
```

Docker gửi SIGTERM rồi chờ tối đa 10 giây mới SIGKILL. Thoát sau **0,515 giây** nghĩa là app **tự nguyện thoát**. Log ghi đủ 4 bước theo đúng thứ tự:

```json
{"timestamp":"...","level":"INFO","event":"signal_received","signum":15}
{"timestamp":"...","level":"INFO","event":"shutdown_started","in_flight":0}
{"timestamp":"...","level":"INFO","event":"drain_complete"}
{"timestamp":"...","level":"INFO","event":"redis_closed"}
{"timestamp":"...","level":"INFO","event":"shutdown_complete"}
```

---

## Câu 8 (CP1) — Vì sao log JSON tốt hơn `print()`?

`print("đã xử lý xong")` chỉ con người đọc được, và cũng chỉ đọc được khi ngồi nhìn màn hình. Log JSON thì:

**1. Máy đọc được.** Grafana, Datadog, CloudWatch parse thẳng thành dashboard, không cần viết regex. Mà regex thì mỗi lần đổi câu chữ trong `print()` là hỏng.

**2. Tìm kiếm được.** Lọc `user_id = "sv01"`, hoặc `level = "ERROR"`, hoặc `latency_ms > 500` chỉ mất vài giây — kể cả trong hàng triệu dòng log.

Định dạng đang dùng (`app/logging_utils.py`):

```json
{"timestamp": "2026-08-10T08:05:33.516Z", "level": "INFO", "event": "ask_completed", "user_id": "sv01", "latency_ms": 116.4, "cost_usd": 1.89e-05}
```

Ba chi tiết đáng chú ý trong cách triển khai:

- **Luôn dùng UTC** (`...Z`). Server ở nhiều múi giờ mà log giờ địa phương thì không thể xếp đúng thứ tự sự kiện khi điều tra sự cố.
- **`force=True`** trong `basicConfig()`. Thiếu nó, nếu một thư viện nào đó lỡ gọi `logging.warning()` trước thì root logger đã có handler, `basicConfig()` sẽ im lặng không làm gì và **toàn bộ log JSON biến mất**. Đây là lỗi thật tôi đã gặp và phải sửa.
- **Gắn formatter cho cả logger của uvicorn**, để log truy cập cũng cùng định dạng — đỡ phải parse hai kiểu khác nhau trong cùng một luồng log.

---

## Câu 9 (CP3) — Vì sao Sliding Window thay vì Fixed Window? Vì sao member phải duy nhất?

**Sliding Window vs Fixed Window.** Fixed Window đếm theo phút chẵn và reset lúc giây 00. Lỗ hổng: user gửi 10 request ở giây **59** và thêm 10 request ở giây **00** — tổng **20 request trong 2 giây**, mà cả hai cửa sổ đều thấy mình chỉ có 10, không vi phạm.

Sliding Window luôn nhìn lại đúng 60 giây gần nhất tính từ thời điểm hiện tại, nên không có "khe hở ở ranh giới". Cái giá phải trả là tốn bộ nhớ hơn: phải lưu mốc thời gian của từng request thay vì chỉ một biến đếm.

**Vì sao member trong Sorted Set phải duy nhất?** Nếu dùng `str(now)` làm member, hai request đến cùng mili-giây sẽ **ghi đè nhau** trong Sorted Set (bản chất Sorted Set không cho trùng member) → đếm thiếu → rate limit bị "lọt". Dùng `f"{now}:{uuid.uuid4().hex}"` đảm bảo mỗi request là một bản ghi riêng biệt.

**Thứ tự 5 bước cũng quan trọng** (`app/rate_limiter.py`):

1. `zremrangebyscore` — xoá entry cũ hơn 60 giây
2. `zcard` — đếm số entry còn lại
3. Nếu `>= limit` → raise 429 và **dừng ở đây, KHÔNG ghi nhận request bị chặn**
4. Còn quota → `zadd` ghi entry mới
5. `expire` — đặt TTL để Redis tự dọn

Bước 3 dừng trước bước 4 là điểm dễ sai nhất: nếu vẫn ghi nhận request đã bị chặn, user bị spam sẽ không bao giờ thoát khỏi trạng thái 429 vì cửa sổ liên tục được làm mới.

**Kiểm chứng** — cấu hình `RATE_LIMIT_PER_MINUTE=10`, bắn 13 request:

```
req 1..10  -> 200
req 11..13 -> 429
```

**Ghi chú production:** đoạn code trên chạy tuần tự nhiều lệnh Redis. Dưới tải lớn, giữa bước `zcard` và bước `zadd` có thể chen vào request khác (race condition). Bản production cần gom các lệnh vào một Lua script để Redis chạy atomic.

---

## Câu 10 (CP5) — Một lỗi gặp khi deploy: thông báo là gì, tìm nguyên nhân thế nào, sửa ra sao?

**Lỗi gặp phải:** deploy lên Railway, build thành công nhưng container khởi động rồi chết ngay, lặp lại liên tục.

**Thông báo lỗi** (lấy từ `railway logs`):

```
Starting Container
Error: Invalid value for '--port': '$PORT' is not a valid integer.
Usage: uvicorn [OPTIONS] APP
```

**Cách tìm ra nguyên nhân.** Thông báo nói uvicorn nhận được **chuỗi ký tự `"$PORT"`** chứ không phải một con số. Nghĩa là biến `$PORT` không được thay bằng giá trị thật. Có hai khả năng: (a) Railway không cấp biến `PORT`, hoặc (b) biến có nhưng không được thay thế.

Tôi loại trừ (a) bằng cách xem tab Variables trên dashboard — `PORT` có được Railway tự inject. Vậy vấn đề nằm ở (b): **ai chịu trách nhiệm thay biến**.

Thủ phạm là dòng này trong `railway.toml`:

```toml
startCommand = "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
```

Railway chạy `startCommand` ở dạng **exec** — gọi thẳng chương trình, **không qua shell**. Mà việc thay `$PORT` thành số là công việc của **shell**. Không có shell thì chuỗi `$PORT` được truyền nguyên văn.

**Cách sửa** — bọc lệnh trong `sh -c` để có shell làm việc thay biến:

```toml
startCommand = "sh -c 'exec uvicorn app.main:app --host 0.0.0.0 --port $PORT'"
```

Từ khoá `exec` cũng quan trọng: nó khiến uvicorn **thay thế** tiến trình `sh` và trở thành PID 1, nhận trực tiếp SIGTERM từ platform. Thiếu `exec` thì `sh` giữ PID 1 và không chuyển tín hiệu xuống uvicorn, graceful shutdown sẽ không bao giờ chạy.

**Bài học rút ra:** khi thấy tên biến xuất hiện *nguyên văn* trong thông báo lỗi (`'$PORT' is not a valid integer`), gần như chắc chắn là lệnh đang chạy ở dạng exec chứ không qua shell. Đây là khác biệt thật giữa các nền tảng — Render chạy start command **qua shell** nên `$PORT` hoạt động bình thường, không cần bọc `sh -c`.

**Một lỗi thứ hai cũng đáng ghi lại:** lần đầu chạy `railway up`, code app bị deploy đè lên **service Redis**. Nguyên nhân: sau lệnh `railway add --database redis`, CLI tự động link vào service Redis vừa tạo, và `railway up` deploy vào service đang được link. Cách phòng: luôn chạy `railway status` để xác nhận service đang link trước khi `up`, và ghi rõ `railway up --service <tên-app>`.
