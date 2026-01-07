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


# Tôi muốn tra cứu thông tin thửa đất số 177, tờ bản đồ 37
# Ngoài ra, cho tôi biết luôn thửa 178 trên cùng tờ 37 có cùng mục đích sử dụng không?
# Bên cạnh đó, thửa 274 ở tờ 37 thì sao? Có được xây nhà ở không?
# Tạo bảng so sánh 3 thửa đất trên.

#12.2282 109.1927