from pathlib import Path
import torch
import json
from .loader import get_model_and_tokenizer
from .function_registry import functions
from .function_executor import execute_function
from .prompts import SYSTEM_PROMPT
from transformers import TextIteratorStreamer, StoppingCriteriaList
from .stopping import StopByConversation
from threading import Thread
from .state import StateManager

"""
- Tìm kiếm function từ câu hỏi
- Trích xuất tham số cho function
"""


#   khởi tạo agent
class FunctionAgent:
    def __init__(self):
        """
        Khởi tạo agent: load model + chuẩn bị tokenizer.
        """

        MODEL_PATH = "Qwen/Qwen3-4B-Instruct-2507"
        self.model, self.tokenizer = get_model_and_tokenizer(str(MODEL_PATH))
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.eval()

    
    # function xử lý yêu cầu từ prompt 
    def llm_generate(self, messages, max_tokens=64):
        """
        Hàm chuẩn sinh text từ LLM.
        """
        
        tokenized = self.tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model.generate(
                **tokenized,
                max_new_tokens=max_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
            )

        # Lấy phần sinh thêm
        output_text = self.tokenizer.decode(
            outputs[0][tokenized["input_ids"].shape[1]:],
            skip_special_tokens=True
        )

        return output_text.strip()

    # tìm kiếm function 
    def find_function(self, name: str):
        """
        Tìm hàm trong registry.
        """
        for fn in functions:
            if fn["name"].lower() == name.lower():
                return fn
        return None

    # parse text to json
    def safe_parse_json(self, text: str):
        try:
            return json.loads(text.strip())
        except Exception:
            return {}
        
    def rewrite_query(self, history, new_user_input):
        if not history:
            return new_user_input

        # Lấy 4 lượt gần nhất (2 cặp User-AI) là đủ để hiểu đại từ
        # 6 lượt có thể khiến model 4B bị nhiễu thông tin cũ
        recent_history = history[-4:] 

        # Gom lịch sử thành một khối văn bản để LLM dễ bao quát
        history_str = ""
        for msg in recent_history:
            role_label = "Người dùng" if msg["role"] == "user" else "Trợ lý"
            history_str += f"{role_label}: {msg['content']}\n"

        # Tạo prompt theo dạng Instruction rõ ràng
        user_content = f"--- LỊCH SỬ TRÒ CHUYỆN ---\n{history_str}\n\n--- CÂU HỎI MỚI NHẤT ---\n{new_user_input}"

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT["rewrite_query"].strip()},
            {"role": "user", "content": user_content}
        ]

        # Debug để kiểm tra format gửi đi
        # print("Message step 0: ", messages)

        standalone_query = self.llm_generate(messages, max_tokens=256)
        
        # Xử lý trường hợp model 4B lặp lại tiền tố thừa
        final_query = standalone_query.strip()
        return final_query.strip()

    
    def select_function(self, history, user_query: str) -> str:
        """
        Chọn function dựa trên câu hỏi hiện tại của user.
        Không dùng history để tối giản và tăng tốc.
        """
        # --- Sinh danh sách function để đưa vào prompt ---
        function_list = "\n".join(
            f"{fn['name']}: {fn['description']}" for fn in functions
        )

        recent_history = history[-6:]  # Giữ nguyên dict {"role": ..., "content": ...}

        SYSTEM_PROMPT_STEP1 = SYSTEM_PROMPT["function_selection"].format(
            function_list=function_list
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_STEP1},
            *recent_history,
            {"role": "user", "content": user_query}
        ]

        print("Message step 1: ", messages)

        raw_fn_name = self.llm_generate(
            messages,
            max_tokens=32,
        )

        fn_name = raw_fn_name.strip().lower()
        return fn_name


    def extract_params(self, fn_name, history, user_query):
        # Nếu LLM nói "None" → coi như câu hỏi đơn thuần
        if fn_name in ["none", "null", "", "no_function"]:
            return {}

        # Kiểm tra tồn tại
        function_info = self.find_function(fn_name)
        if function_info is None:
            return {}

        param_parts = []
        for p_name, p_info in function_info["parameters"].items():
            type = p_info.get("type", "string")
            desc = p_info.get("description", "không có mô tả")
            example = p_info.get("example", "không có")
            param_parts.append(f"- {p_name} ({type}): {desc} (ví dụ: {example})")

        param_list = "\n".join(param_parts)

        step2_prompt = SYSTEM_PROMPT["parameter_extraction"].format(
            function_name=function_info['name'],
            param_list=param_list or "không yêu cầu tham số"
        )

        recent_history = history[-6:]  # Giữ nguyên dict {"role": ..., "content": ...}

        messages_step2 = [
            {"role": "system", "content": step2_prompt},
            *recent_history,
            {"role": "user", "content": user_query}
        ]

        print("Message step 2: ", messages_step2)

        max_tokens = 128
        if (fn_name == "tom_tat_van_ban"):
            max_tokens = 1024
        raw_params = self.llm_generate(messages_step2, max_tokens)
        
        arguments = self.safe_parse_json(raw_params)
        return arguments

    # hàm chính gọi function calling + trích xuất tham số
    def call_function (self, fn, final_params) -> dict:
        result = execute_function(fn, final_params)
        result["function"] = fn
        return result
    
    def demo(self, history, user_query: str):
        """
        Hàm demo quy trình xử lý yêu cầu từ user.
        """
        messages = [{"role": "system", "content": SYSTEM_PROMPT["demo"]}]
        messages.extend(history)  # history đã có định dạng đúng
        messages.append({"role": "user", "content": user_query})

        print("Step 1 messages: ", messages)

        result = self.llm_generate(
            messages,
            max_tokens=256,      # đủ cho JSON output (~100–200 token)
        )
        
        return self.safe_parse_json(result)


    # -----------------------------------------
    # Hàm stream trả lời từ LLM
    # -----------------------------------------
    def stream_llm_answer(self, system_prompt: str, state_manager: StateManager, user_query: str, max_tokens=256):
        # Reset cờ stop trong state
        state_dict = state_manager.get()
        state_dict["stop"] = False
        
        recent_history = state_manager.conversation["history"][-4:]
        messages = [{"role": "system", "content": system_prompt},
                    *recent_history,
                    # {"role": "user", "content": user_query}
                    ]

        print("Messages step 3: ", messages)
        tokenized = self.tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True
        ).to(self.device)

        streamer = TextIteratorStreamer(
            self.tokenizer,
            skip_prompt=True,
            skip_special_tokens=True
        )

        # StopByConversation cần dict để kiểm tra "stop"
        stopping_criteria = StoppingCriteriaList([
            StopByConversation(state_dict)  # truyền dict, không phải StateManager
        ])

        generation_kwargs = dict(
            **tokenized,
            streamer=streamer,
            max_new_tokens=max_tokens,
            do_sample=True,
            use_cache=True,
            pad_token_id=self.tokenizer.eos_token_id,
            eos_token_id=self.tokenizer.eos_token_id,
            stopping_criteria=stopping_criteria
        )

        thread = Thread(target=self.model.generate, kwargs=generation_kwargs, daemon=True)
        thread.start()

        full_answer = ""
        for new_text in streamer:
            full_answer += new_text
            yield new_text

        # Lưu lại tin nhắn assistant vào trạng thái
        state_manager.add_assistant_message(full_answer)
        print("Done!")