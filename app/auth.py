"""
CP3 — Xác thực API Key.

Mỗi request phải có header `X-API-Key` khớp với `AGENT_API_KEY` trong .env.
Sai hoặc thiếu → 401 Unauthorized.
"""
import hmac

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from app.config import settings

# auto_error=False → tự quyết định thông báo lỗi thay vì để FastAPI trả về
# câu mặc định khó hiểu.
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """
    Dependency của FastAPI. Gắn `Depends(verify_api_key)` vào endpoint nào
    thì endpoint đó được bảo vệ.

    Returns:
        API key hợp lệ.

    Raises:
        HTTPException 401 khi thiếu hoặc sai key.
    """
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Include header: X-API-Key: <your-key>",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # hmac.compare_digest so sánh trong thời gian hằng định, không phụ thuộc
    # hai chuỗi giống nhau tới ký tự thứ mấy. Toán tử `==` thoát ra ngay khi
    # gặp ký tự khác nhau đầu tiên, nên kẻ tấn công đo thời gian phản hồi có
    # thể dò ra key từng ký tự một (timing attack).
    if not hmac.compare_digest(api_key, settings.agent_api_key):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return api_key
