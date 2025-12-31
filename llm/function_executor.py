from .function_registry import functions
import json
from typing import Any, Dict, Optional

# Thực thi function được định nghĩa trong function_registry.py

# === Map tên → hàm ===
FUNCTION_REGISTRY = {fn["name"]: fn for fn in functions}


def execute_function(function_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:

    function_info = FUNCTION_REGISTRY.get(function_name)
    func = function_info["callable"]

    try:
        result = func(arguments)
        return result

    except TypeError as e:
        error_msg = str(e)
        if "missing" in error_msg:
            missing = error_msg.split("'")[1] if "'" in error_msg else "unknown"

            des_missing = function_info["parameters"].get(missing, {}).get("description", missing)

            return {
                "status": "incomplete",
                "message": f"Vui lòng cung cấp: {missing} ({des_missing})"
            }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Đã xảy ra lỗi: {str(e)}"
        }
