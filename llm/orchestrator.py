from .prompts import USER_ANSWER_PROMPT   # đặt trong prompts.py
from .state import StateManager
from .agent import FunctionAgent
from .function_registry import functions
from string import Template

"""
- Tạo câu trả lời cho người dùng
"""

# -----------------------------------------
# Orchestrator: điều phối toàn bộ workflow
# -----------------------------------------

class Orchestrator:
    def __init__(self, conversation_id: str, agent: FunctionAgent):
        self.agent = agent   # sử dụng agent chuẩn
        self.state = StateManager(conversation_id)

    def resolve_params(self, fn, extracted_params, state):
        fn_info = self.agent.find_function(fn)

        if (fn_info is None):
            return {}, []

        valid_params = fn_info["parameters"].keys()
        required_params = fn_info.get("required", [])

        # Chỉ dùng entity trong state nếu intent khớp
        state_entities = {}
        if isinstance(state, dict) and state.get("current_intent") == fn:
            state_entities = state.get("entities", {})

        final_params = {}

        for p in valid_params:
            if extracted_params.get(p) is not None:
                final_params[p] = extracted_params[p]
            elif state_entities.get(p) is not None:
                final_params[p] = state_entities[p]

        missing = [
            p for p in required_params
            if final_params.get(p) in (None, "", "None")
        ]

        return final_params, missing



    # ------------------------------------------------------
    # Build final answer cho người dùng sau khi gọi function
    # ------------------------------------------------------
    def build_user_answer(self, user_query: str):
        if self.state is None:
            raise RuntimeError("State chưa được load. Hãy gọi load_state(conversation_id)")
        
        # Lưu câu hỏi người dùng
        self.state.add_user_message(user_query)

        history = self.state.conversation.get("history", [])

        # DEMO

        

        # 1. Gọi LLM để ra quyết định
        # llm_output = self.agent.demo(history[-3:-1], user_query)

        # print("LLM Output: ", llm_output)

        # if not llm_output:
        #     # fallback nếu LLM lỗi
        #     fn = "hoi_thoai_chung"
        #     final_params = {}
        # else:
        #     fn = llm_output.get("function_name", "hoi_thoai_chung")
        #     final_params = llm_output.get("parameters", {})

        # STEP 0: chuyển câu hỏi mới thành câu đơn nhất

        user_query = self.agent.rewrite_query(history[:-1], user_query)

        print("step 0: ", user_query)

        # STEP 1: chọn function
        fn = self.agent.select_function([], user_query)
        
        print("step 1: ", fn)

        is_fn = self.agent.find_function(fn)

        # Không có function phù hợp → chỉ chat bình thường
        if not fn or fn == "none" or is_fn is None:
            full_answer = "Xin lỗi, nhưng câu hỏi của bạn không thuộc phạm vi trách nhiệm của tôi. Nếu bạn cần hỗ trợ về lĩnh vực quy hoạch của tỉnh Khánh Hòa, hãy cho tôi biết!"
            self.state.add_assistant_message(full_answer)
            return full_answer

        self.state.update_state({
            "current_intent": fn,
            "status": "collecting",
            "entities": {},
            "missing": []
        })

        # STEP 2: trích params
        fn_info = self.agent.find_function(fn)
        valid_params = fn_info["parameters"].keys()

        params = {}
        if valid_params:
            params = self.agent.extract_params(fn, [], user_query)

        print("step 2: ", params)

        self.state.update_state({
            "entities": params
        })

        final_params, missing = self.resolve_params(
            fn=fn,
            extracted_params=params or {},
            state=self.state.conversation.get("state")
        )

        self.state.update_state({
            "missing": missing,
            "status": "ready" if not missing else "collecting"
        })

        print("Missing: ", missing)

        if missing:
            missing_descriptions = []
            for p in missing:
                desc = fn_info.get("parameters", {}).get(p, {}).get("description", p)
                missing_descriptions.append(desc)

            lookup_text = "\n".join(f"- {d}" for d in missing_descriptions)

            return self.agent.stream_llm_answer(
                USER_ANSWER_PROMPT["incomplete"].format(
                    lookup_result=lookup_text
                ),
                self.state,
                user_query=user_query
            )
        
        # STEP 3: gọi function
        result = self.agent.call_function(fn, final_params)

        print("step 3: ", result)

        self.state.update_state({
            "status": "done"
        })
        
        status = result["status"]
        max_tokens = 256
        
        # Không có function phù hợp → chỉ chat bình thường
        if not result or status == "normal":
            system_prompt = USER_ANSWER_PROMPT[status].format(
                result="Câu hỏi này không cần dữ liệu."
            )
            # note: sửa lại truyền user_query
            return self.agent.stream_llm_answer(
                system_prompt=system_prompt,
                state_manager=self.state,
                user_query=user_query,
                max_tokens=512
            )

        # Tạo dữ liệu để đưa vào prompt
        if status == "success":
            desc = result.get("field_descriptions", {})
            function_name = fn
            data = result.get("data", {})

            self.state.update_context(function_name, data)

            data_lines = [
                f"- {desc.get(k, k)}: {v}"
                for k, v in result["data"].items()
                if v not in (None, "", "None")
            ]

            lookup_text = "\n".join(data_lines)

            # 👇 BỔ SUNG: xử lý suggestion templates với params
            SUGGESTION_TEMPLATES = fn_info.get("suggestion_templates", [])
            suggestions = [
                tpl.format(**final_params)
                for tpl in SUGGESTION_TEMPLATES
            ]

            suggestion_templates = "\n".join(f"- {s}" for s in suggestions)
            max_tokens=512

        elif status == "incomplete" or status == "not_found" or status == "summary":
            lookup_text = result.get("message", "")
            max_tokens=256
        else:
            lookup_text = ""

        # print('Data: ', lookup_text)
        # Tạo system prompt cuối
        system_prompt = USER_ANSWER_PROMPT[status].format(
            lookup_result=lookup_text,
            suggestion_templates=suggestion_templates if status == "success" else "Không có"
        )

        # print("Final System Prompt:\n", system_prompt)

        # Trả về dạng stream
        return self.agent.stream_llm_answer(system_prompt, self.state, user_query, max_tokens)
    

