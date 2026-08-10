"""
✅ ADVANCED — Centralized Config Management (12-Factor: Config in Env)

Tất cả config đọc từ environment variables.
- Không có giá trị nhạy cảm trong code
- Dễ thay đổi giữa dev/staging/production
- Validation rõ ràng — fail fast nếu thiếu config quan trọng
"""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# ✅ FIX: nạp file .env vào os.environ TRƯỚC khi Settings đọc config.
# Thiếu dòng này thì `cp .env.example .env` hoàn toàn vô tác dụng.
# override=False (mặc định) → env var thật của OS/cloud platform vẫn được ưu tiên
# hơn file .env, đúng tinh thần 12-Factor.
load_dotenv()


@dataclass
class Settings:
    # Server
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")

    # App
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "AI Agent"))
    app_version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "1.0.0"))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))

    # LLM (optional — chỉ warn nếu thiếu, không crash)
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini"))
    max_tokens: int = field(default_factory=lambda: int(os.getenv("MAX_TOKENS", "500")))

    # Security
    api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))
    allowed_origins: list = field(
        default_factory=lambda: os.getenv("ALLOWED_ORIGINS", "*").split(",")
    )

    # ✅ FIX: gom cảnh báo vào đây thay vì log ngay lúc import (xem validate()).
    startup_warnings: list = field(default_factory=list)

    def validate(self):
        """Fail fast nếu thiếu config bắt buộc."""
        # ✅ FIX: KHÔNG gọi logging.warning() ở đây.
        # File này được import trước khi app.py kịp gọi logging.basicConfig().
        # Gọi logging.warning() ở module level sẽ ngầm kích hoạt basicConfig()
        # với level WARNING + format mặc định, khiến cấu hình JSON logging của
        # app.py bị vô hiệu hoá. Thay vào đó chỉ gom cảnh báo lại, để app.py
        # tự log ra SAU khi logging đã được cấu hình đúng.
        if not self.openai_api_key:
            self.startup_warnings.append("OPENAI_API_KEY not set — using mock LLM")
        if not self.api_key and self.environment == "production":
            # Lỗi nghiêm trọng thì vẫn fail fast ngay lập tức
            raise ValueError("AGENT_API_KEY must be set in production!")
        return self


# Singleton — import từ bất kỳ file nào đều dùng chung
settings = Settings().validate()
