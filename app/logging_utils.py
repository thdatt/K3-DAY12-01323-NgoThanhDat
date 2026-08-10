"""
CP1 — Structured logging dạng JSON.

Thay `print("đã xử lý xong")` bằng log JSON có cấu trúc:

    {"timestamp": "2026-08-09T10:30:00Z", "level": "INFO",
     "event": "ask_completed", "user_id": "sv01", "latency_ms": 812}

Vì sao phải JSON?
  1. Máy đọc được — Grafana, Datadog, CloudWatch parse và dựng dashboard tự động.
  2. Tìm kiếm được — lọc theo user_id, level, hoặc latency_ms > 500 trong vài giây.

Log dạng câu chữ tự do thì phải viết regex mới bóc được thông tin, và mỗi lần
đổi câu chữ là regex hỏng.
"""
import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """
    Formatter biến mỗi bản ghi log thành một dòng JSON.

    Mọi trường phụ truyền qua `extra=` đều được gộp thẳng vào JSON, nhờ vậy
    `logger.info("...", extra={"user_id": "sv01"})` sẽ có khoá `user_id` ở
    cấp cao nhất — đúng dạng mà công cụ giám sát mong đợi.
    """

    # Các thuộc tính có sẵn của LogRecord — không phải trường do ta thêm vào
    _RESERVED = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "taskName", "message", "asctime",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            # Định dạng ISO-8601 kết thúc bằng "Z" = múi giờ UTC.
            # Luôn log theo UTC: server ở nhiều múi giờ mà log giờ địa phương
            # thì không thể xếp đúng thứ tự sự kiện khi điều tra sự cố.
            "timestamp": datetime.now(timezone.utc)
                                 .isoformat(timespec="milliseconds")
                                 .replace("+00:00", "Z"),
            "level": record.levelname,
            "event": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # ensure_ascii=False để tiếng Việt hiện đúng chữ thay vì \uXXXX
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO") -> logging.Logger:
    """
    Cấu hình logging JSON cho toàn app.

    force=True ép ghi đè mọi handler đã tồn tại. Thiếu nó, nếu một thư viện
    nào đó lỡ gọi logging.warning() trước ta thì root logger đã có handler,
    basicConfig() sẽ im lặng không làm gì và toàn bộ log JSON biến mất.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=[handler],
        force=True,
    )

    # uvicorn tự cấu hình logger riêng — gắn formatter JSON cho chúng luôn
    # để log truy cập cũng cùng định dạng, đỡ phải parse 2 kiểu.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = [handler]
        lg.propagate = False

    return logging.getLogger("agent")


logger = logging.getLogger("agent")
