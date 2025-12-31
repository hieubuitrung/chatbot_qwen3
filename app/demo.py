import sys
from pathlib import Path

# ================================
# Thêm thư mục gốc vào PYTHONPATH
# ================================
ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT))

from llm.orchestrator import Orchestrator

# ================================
# Tạo chatbot
# ================================
orc = Orchestrator()


print("=== Chatbot Quy Hoạch Khánh Hòa ===")
print("Gõ 'exit' để thoát.")
print("------------------------------------")

while True:
    user_input = input("Bạn: ").strip()

    if user_input.lower() in ["exit", "quit"]:
        print("🤖 Assistant: Tạm biệt!")
        break

    # Stream phản hồi
    print("🤖 Assistant: ", end="", flush=True)
    full_response = ""
    orc.load_state("conv_20251216_145012")

    for token in orc.build_user_answer(user_input):
        full_response += token
        print(token, end="", flush=True)

    print("\n")  # xuống dòng giữa mỗi lượt


# - Số tờ bản đồ: 37
# - Số thửa đất: 177/274

#12.2282 109.1927