"""
Authentication — xác thực bằng API key.

Tách riêng khỏi main.py theo đúng cấu trúc mà DAY12_DELIVERY_CHECKLIST.md
yêu cầu, đồng thời để logic bảo mật nằm gọn một chỗ, dễ đọc và dễ test.
"""
import hmac

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from app.config import settings

# auto_error=False → tự mình quyết định thông báo lỗi, thay vì để FastAPI
# trả về câu mặc định khó hiểu.
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _valid_keys() -> set[str]:
    """
    Danh sách key hợp lệ.

    Hỗ trợ NHIỀU key ngăn cách bởi dấu phẩy để xoay key không cần downtime:
        thêm key mới → báo client đổi sang key mới → gỡ key cũ
    Chỉ có một key thì mỗi lần đổi là toàn bộ client gãy cùng lúc.
    """
    return {k.strip() for k in settings.agent_api_key.split(",") if k.strip()}


def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    Dependency của FastAPI: gắn `Depends(verify_api_key)` vào endpoint nào
    thì endpoint đó được bảo vệ.

    Returns:
        Chính API key đã dùng — main.py lấy nó làm định danh cho rate limit
        và cost guard.

    Raises:
        401 nếu thiếu key, 403 nếu key sai.
    """
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Include header: X-API-Key: <your-key>",
        )

    # hmac.compare_digest so sánh trong thời gian hằng định, không phụ thuộc
    # vào việc hai chuỗi giống nhau tới ký tự thứ mấy. Toán tử `==` thoát ra
    # ngay khi gặp ký tự khác nhau đầu tiên, nên kẻ tấn công đo thời gian
    # phản hồi có thể dò ra key từng ký tự một (timing attack).
    for valid in _valid_keys():
        if hmac.compare_digest(api_key, valid):
            return api_key

    raise HTTPException(status_code=403, detail="Invalid API key.")


def key_identity(api_key: str) -> str:
    """
    Rút gọn API key thành định danh ngắn để làm khoá cho rate limit / budget.

    KHÔNG dùng nguyên API key làm khoá Redis: khoá Redis hay xuất hiện trong
    log, trong công cụ giám sát, trong lệnh `KEYS *` khi debug — đưa nguyên
    secret vào đó là tự làm lộ.
    """
    return api_key[:8]
