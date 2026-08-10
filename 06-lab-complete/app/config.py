"""Production config — 12-Factor: tất cả từ environment variables."""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# ✅ Nạp file .env vào os.environ TRƯỚC khi Settings đọc config.
# override=False (mặc định) → biến môi trường thật do cloud platform inject
# (ví dụ PORT của Railway) vẫn thắng file .env. Đúng thứ tự ưu tiên 12-Factor:
#   env thật của OS/cloud  >  file .env  >  giá trị mặc định trong code
load_dotenv()


@dataclass
class Settings:
    # Server
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")

    # App
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "Production AI Agent"))
    app_version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "1.0.0"))

    # LLM
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini"))

    # Security
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", "dev-key-change-me"))
    jwt_secret: str = field(default_factory=lambda: os.getenv("JWT_SECRET", "dev-jwt-secret"))
    allowed_origins: list = field(
        default_factory=lambda: os.getenv("ALLOWED_ORIGINS", "*").split(",")
    )

    # Rate limiting
    rate_limit_per_minute: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))
    )

    # Budget
    daily_budget_usd: float = field(
        default_factory=lambda: float(os.getenv("DAILY_BUDGET_USD", "5.0"))
    )
    global_daily_budget_usd: float = field(
        default_factory=lambda: float(os.getenv("GLOBAL_DAILY_BUDGET_USD", "50.0"))
    )

    # Storage
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", ""))

    # ✅ Gom cảnh báo lại đây thay vì log ngay lúc import — xem validate()
    startup_warnings: list = field(default_factory=list)

    def validate(self):
        """Fail fast: thiếu config sống còn thì crash ngay lúc khởi động."""
        # ✅ KHÔNG gọi logging.warning() trong hàm này.
        # File config được import trước khi main.py kịp gọi logging.basicConfig().
        # Gọi logging.warning() ở thời điểm đó sẽ ngầm kích hoạt basicConfig()
        # với format mặc định, khiến cấu hình JSON logging của main.py thành
        # vô tác dụng và mọi logger.info() bị nuốt mất.
        if self.environment == "production":
            if self.agent_api_key == "dev-key-change-me":
                raise ValueError("AGENT_API_KEY must be set in production!")
            if self.jwt_secret == "dev-jwt-secret":
                raise ValueError("JWT_SECRET must be set in production!")
            if not self.redis_url:
                # Cảnh báo chứ không crash: vẫn có thể chạy 1 instance không Redis
                self.startup_warnings.append(
                    "REDIS_URL chưa đặt trong production — rate limit và budget "
                    "sẽ đếm riêng trên từng instance, số liệu sẽ SAI khi scale."
                )
        if not self.openai_api_key:
            self.startup_warnings.append("OPENAI_API_KEY not set — using mock LLM")
        return self


settings = Settings().validate()
