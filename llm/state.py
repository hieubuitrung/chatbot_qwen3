# llm/state_manager.py
import os
import json
from datetime import datetime
from threading import Lock
from typing import List, Dict, Any, Optional
from pathlib import Path

class StateManager:
    """
    State tổng quát cho chatbot (DEMO version).
    Mỗi conversation = 1 file JSON.
    """

    _stop_flags = {}
    _stop_lock = Lock()

    def __init__(self, conversation_id: str, max_history=6, data_dir="data/conversations"):
        self.conversation_id = conversation_id
        self.max_history = max_history
        self.data_dir = data_dir

        self.conversation = {}

        os.makedirs(self.data_dir, exist_ok=True)
        self.file_path = Path(self.data_dir) / f"{conversation_id}.json"

        self._load()

        
    def get(self):
        with self.__class__._stop_lock:
            return self.__class__._stop_flags.setdefault(self.conversation_id, {"stop": False})

    def stop(self):
        with self.__class__._stop_lock:
            flag = self.__class__._stop_flags.setdefault(self.conversation_id, {"stop": False})
            flag["stop"] = True
    
    

    # -----------------------------
    # File IO
    # -----------------------------
    def _load(self):
        """Load state từ file nếu tồn tại"""
        if not os.path.exists(self.file_path):
            self._init_file()
            return

        with open(self.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.conversation = data

    def _save(self):
        """Lưu state hiện tại ra file"""
        payload = {
            "conversation_id": self.conversation_id,
            "history": self.conversation.get("history", []),
            "state": self.conversation.get("state", {}),
            "context": self.conversation.get("context", {}),
            "updated_at": datetime.utcnow().isoformat(),
        }

        # nếu file chưa tồn tại → thêm created_at
        if not os.path.exists(self.file_path):
            payload["created_at"] = payload["updated_at"]
        else:
            with open(self.file_path, "r", encoding="utf-8") as f:
                old = json.load(f)
            payload["created_at"] = old.get("created_at")

        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _init_file(self):
        """Tạo file conversation mới"""
        self.conversation = {}
        self._save()

    # -----------------------------
    # Lịch sử hội thoại
    # -----------------------------
    def add_user_message(self, msg: str):
        self._add_msg("user", msg)

    def add_assistant_message(self, msg: str):
        self._add_msg("assistant", msg)

    def _add_msg(self, role, msg):
        if "history" not in self.conversation:
            self.conversation["history"] = []

        self.conversation["history"].append({
            "role": role,
            "content": msg
        })

        # if len(self.conversation["history"]) > self.max_history:
        #     self.conversation["history"] = self.conversation["history"][-self.max_history:]

        self._save()


    def get_chat_history( self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Lấy lịch sử chat từ file theo conversation_id

        :param conversation_id: id của cuộc hội thoại
        :param limit: số message cuối cùng cần lấy (None = lấy tất cả)
        :return: danh sách message [{role, content}]
        """

        if not os.path.exists(self.file_path):
            return []

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            messages = data.get("history", [])

            if limit is not None:
                return messages[-limit:]

            return messages

        except Exception as e:
            # log nếu cần
            print(f"[StateManager] Error reading state: {e}")
            return []
        

    # -----------------------------
    # Ngữ cảnh function calling
    # -----------------------------
    def update_context(self, function_name: str, data: dict):
        if not isinstance(data, dict):
            return

        if "context" not in self.conversation:
            self.conversation["context"] = {}

        self.conversation["context"][function_name] = data
        self._save()

    def update_state(self, new_state: dict):
        if not isinstance(new_state, dict):
            return

        old_state = self.conversation.get("state", {})

        old_intent = old_state.get("current_intent")
        new_intent = new_state.get("current_intent")

        # Nếu intent đổi → reset state
        if new_intent and new_intent != old_intent:
            self.conversation["state"] = {
                "current_intent": new_intent,
                "entities": new_state.get("entities", {}) or {},
                "missing": new_state.get("missing", []),
                "status": new_state.get("status", "collecting")
            }
        else:
            merged = old_state.copy()
            merged.update(new_state)

            if "entities" in new_state:
                old_entities = old_state.get("entities", {})
                new_entities = new_state.get("entities", {})

                # Chuẩn hoá tuyệt đối
                if not isinstance(old_entities, dict):
                    old_entities = {}
                if not isinstance(new_entities, dict):
                    new_entities = {}

                merged["entities"] = {
                    **old_entities,
                    **new_entities
                }

            self.conversation["state"] = merged

        self._save()



    # -----------------------------
    # Reset
    # -----------------------------
    def clear_context(self):
        self.conversation = {}
        self._save()
