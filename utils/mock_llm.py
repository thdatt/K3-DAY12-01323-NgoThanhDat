"""
Mock LLM — LLM giả lập, không cần API key thật.

Trả lời theo kịch bản có sẵn để cả lab tập trung vào phần deployment thay vì
tốn tiền gọi API. Có mô phỏng độ trễ và tính chi phí theo token để cost guard
có số liệu thật mà làm việc.
"""
import random
import time

# Đơn giá tham khảo của gpt-4o-mini (USD cho mỗi 1000 token)
PRICE_PER_1K_INPUT = 0.00015
PRICE_PER_1K_OUTPUT = 0.0006

MOCK_RESPONSES = {
    "default": [
        "Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.",
        "Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.",
        "Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.",
    ],
    "docker": ["Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"],
    "deploy": ["Deployment là quá trình đưa code từ máy bạn lên server để người khác dùng được."],
    "health": ["Agent đang hoạt động bình thường. All systems operational."],
    "redis": ["Redis là bộ nhớ dùng chung nằm ngoài tiến trình, giúp nhiều instance chia sẻ state."],
}


def estimate_tokens(text: str) -> int:
    """
    Ước lượng số token. Quy ước đơn giản cho lab: 1 từ ~ 2 token.

    Thư viện thật (tiktoken) đếm chính xác hơn, nhưng ở đây chỉ cần một con
    số ổn định để cost guard cộng dồn.
    """
    return max(1, len(text.split()) * 2)


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Quy đổi số token thành tiền USD."""
    return (input_tokens / 1000) * PRICE_PER_1K_INPUT + \
           (output_tokens / 1000) * PRICE_PER_1K_OUTPUT


def ask(question: str, delay: float = 0.1) -> str:
    """Mock LLM call, trả về chuỗi trả lời."""
    time.sleep(delay + random.uniform(0, 0.05))  # mô phỏng độ trễ mạng

    question_lower = question.lower()
    for keyword, responses in MOCK_RESPONSES.items():
        if keyword in question_lower:
            return random.choice(responses)

    return random.choice(MOCK_RESPONSES["default"])


def ask_llm(question: str, history: list | None = None, delay: float = 0.1) -> dict:
    """
    Gọi LLM giả lập, trả về cả nội dung lẫn chi phí.

    Đây là hàm mà `/ask` dùng: cost guard cần `cost_usd` để cộng dồn vào Redis.

    Args:
        question: câu hỏi của người dùng
        history:  lịch sử hội thoại (ảnh hưởng số token đầu vào, giống LLM thật)

    Returns:
        {
          "answer": str,
          "input_tokens": int,
          "output_tokens": int,
          "cost_usd": float,
          "latency_ms": float,
        }
    """
    started = time.perf_counter()

    # LLM thật nhận cả lịch sử làm ngữ cảnh, nên hội thoại càng dài càng đắt.
    context = " ".join(m.get("content", "") for m in (history or []))
    input_tokens = estimate_tokens(context + " " + question)

    answer = ask(question, delay=delay)
    output_tokens = estimate_tokens(answer)

    return {
        "answer": answer,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(estimate_cost(input_tokens, output_tokens), 8),
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def ask_stream(question: str):
    """Mock streaming response — yield từng token."""
    for word in ask(question).split():
        yield word + " "
        time.sleep(0.02)
