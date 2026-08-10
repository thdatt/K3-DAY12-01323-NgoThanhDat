"""
CP4 — Graceful shutdown.

Khi cloud platform gửi SIGTERM (ví dụ: khi deploy phiên bản mới), app cần:
  1. Ngừng nhận request mới (trả 503 cho /ready ngay lập tức)
  2. Đợi request đang chạy hoàn thành (tối đa 30 giây)
  3. Đóng kết nối Redis sạch sẽ
  4. Tắt process

Sự khác biệt giữa /health và /ready khi shutdown:

  /health  (Liveness)  — Kiểm tra process còn sống. KHÔNG gọi Redis.
                         Luôn trả 200 cho đến khi process tắt hẳn.
                         KHÔNG được trả 503, vì orchestrator sẽ tưởng container
                         đã chết và giết tiến trình ngay lập tức, trước khi
                         request đang chạy kịp hoàn thành.

  /ready   (Readiness) — Kiểm tra kết nối Redis.
                         Trả 503 LẬP TỨC khi nhận SIGTERM, để Load Balancer
                         ngắt traffic, không gửi request mới vào nữa.
"""
import asyncio
import signal
import time

from app.logging_utils import logger

DRAIN_TIMEOUT_SECONDS = 30


class Lifecycle:
    """Theo dõi trạng thái vòng đời của app và số request đang xử lý."""

    def __init__(self):
        self._shutting_down = False
        self._in_flight = 0
        self._started_at = time.time()
        self._previous_sigterm = None

    # ── Trạng thái ────────────────────────────────────────────
    @property
    def is_shutting_down(self) -> bool:
        return self._shutting_down

    @property
    def in_flight(self) -> int:
        return self._in_flight

    @property
    def uptime_seconds(self) -> float:
        return round(time.time() - self._started_at, 1)

    def is_ready(self) -> bool:
        """Sẵn sàng nhận request mới không? Đang tắt dần thì không."""
        return not self._shutting_down

    # ── Đếm request đang xử lý ────────────────────────────────
    def enter_request(self) -> None:
        self._in_flight += 1

    def exit_request(self) -> None:
        # Dùng max(0, ...) để phòng trường hợp middleware bị gọi lệch nhịp,
        # tránh biến đếm tụt xuống âm rồi kẹt vòng chờ mãi mãi.
        self._in_flight = max(0, self._in_flight - 1)

    # ── Shutdown ──────────────────────────────────────────────
    def begin_shutdown(self) -> None:
        """
        Bật cờ tắt dần. Gọi ngay khi nhận SIGTERM, TRƯỚC vòng chờ, để /ready
        lập tức trả 503 và Load Balancer ngừng đẩy traffic vào. Không có bước
        này thì vừa chờ vừa nhận thêm request mới, không bao giờ tắt xong.
        """
        if not self._shutting_down:
            self._shutting_down = True
            logger.info("shutdown_started", extra={"in_flight": self._in_flight})

    async def drain(self, timeout: float = DRAIN_TIMEOUT_SECONDS) -> None:
        """Đợi các request đang chạy hoàn thành, tối đa `timeout` giây."""
        self.begin_shutdown()
        deadline = time.time() + timeout

        while self._in_flight > 0 and time.time() < deadline:
            logger.info("draining", extra={"in_flight": self._in_flight})
            await asyncio.sleep(0.5)

        if self._in_flight > 0:
            logger.warning("drain_timeout", extra={"in_flight": self._in_flight})
        else:
            logger.info("drain_complete")

    # ── Signal handler ────────────────────────────────────────
    def install_signal_handlers(self) -> None:
        """
        Bắt SIGTERM để bật cờ tắt dần SỚM NHẤT có thể.

        Quan trọng: sau khi ghi nhận, phải gọi tiếp handler cũ để uvicorn
        thực hiện shutdown như bình thường. Đăng ký handler mà không gọi tiếp
        handler cũ là VÔ HIỆU HOÁ hành vi mặc định — app sẽ nhận SIGTERM, ghi
        log, rồi chạy tiếp như chưa có gì xảy ra, và platform buộc phải
        SIGKILL sau khi hết thời gian chờ.
        """
        self._previous_sigterm = signal.getsignal(signal.SIGTERM)

        def handler(signum, frame):
            logger.info("signal_received", extra={"signum": signum})
            self.begin_shutdown()

            prev = self._previous_sigterm
            if callable(prev):
                prev(signum, frame)
            else:
                # Handler cũ là SIG_DFL/SIG_IGN (không gọi trực tiếp được):
                # trả về mặc định rồi tự gửi lại tín hiệu cho chính mình.
                import os
                signal.signal(signal.SIGTERM, signal.SIG_DFL)
                os.kill(os.getpid(), signal.SIGTERM)

        try:
            signal.signal(signal.SIGTERM, handler)
        except ValueError:
            # signal.signal() chỉ chạy được ở luồng chính. Khi app được import
            # trong worker/test thì bỏ qua, không phải lỗi.
            logger.warning("signal_handler_skipped_not_main_thread")


lifecycle = Lifecycle()
