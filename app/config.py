"""
CP1 — Settings 12-Factor.

Toàn bộ cấu hình đọc từ biến môi trường (hoặc file .env khi chạy local).
Không hardcode giá trị nhạy cảm trong code.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


# Các giá trị placeholder bị coi là "chưa cấu hình" — app phải chết ngay
# thay vì chạy với key giả.
PLACEHOLDER_KEYS = {
    "",
    "changeme",
    "change-me",
    "your-api-key",
    "your_api_key",
    "dev-key-change-me",
    "replace-me",
    "todo",
    "xxx",
}


class Settings(BaseSettings):
    port: int = 8000
    agent_api_key: str                      # Bắt buộc — app chết ngay nếu thiếu (fail-fast)
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_per_minute: int = 10
    monthly_budget_usd: float = 10.0
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def _validate(s: "Settings") -> "Settings":
    """
    Fail-fast: chặn app khởi động khi AGENT_API_KEY còn để trống hoặc vẫn là
    giá trị placeholder.

    Vì sao `agent_api_key` KHÔNG có giá trị mặc định? Nếu để mặc định
    "changeme", app sẽ khởi động bình thường nhưng chạy với key giả — ai cũng
    đoán được và gọi được API. Chết sớm buộc người deploy phải cung cấp key
    thật TRƯỚC khi service nhận request đầu tiên.
    """
    if s.agent_api_key.strip().lower() in PLACEHOLDER_KEYS:
        raise ValueError(
            "AGENT_API_KEY chưa được cấu hình (đang để trống hoặc còn là "
            "placeholder). Đặt biến môi trường AGENT_API_KEY bằng một chuỗi "
            "ngẫu nhiên trước khi chạy app."
        )
    return s


# Singleton — import từ bất kỳ module nào đều dùng chung một instance.
# Pydantic tự raise ValidationError nếu thiếu AGENT_API_KEY hoàn toàn.
settings = _validate(Settings())
