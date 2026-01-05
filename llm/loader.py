# loader.py

from transformers import AutoTokenizer, AutoModelForCausalLM
import torch
from pathlib import Path
from typing import Tuple

"""
- Load model LLM
"""

_model = None
_tokenizer = None
_loaded_model_path = None

def get_model_and_tokenizer(model_path: str) -> Tuple[AutoModelForCausalLM, AutoTokenizer]:
    """
    Trả về (model, tokenizer). Cache để tránh load lại.
    Tự động chọn device_map nếu có GPU.
    """
    global _model, _tokenizer, _loaded_model_path

    model_path = str(Path(model_path).expanduser())

    if _model is not None and _tokenizer is not None and _loaded_model_path == model_path:
        return _model, _tokenizer

    print(f"Đang tải model/tokenizer từ: {model_path}")

    # Tokenizer
    _tokenizer = AutoTokenizer.from_pretrained(
        model_path,
        trust_remote_code=False,
        use_fast=True
    )
    if _tokenizer.pad_token is None:
        _tokenizer.pad_token = _tokenizer.eos_token

    # Model: chọn device_map tự động nếu có CUDA
    has_cuda = torch.cuda.is_available()
    device_map = "auto" if has_cuda else "cpu"

    _model = AutoModelForCausalLM.from_pretrained(
        model_path,
        device_map=device_map,
        torch_dtype=torch.float16 if has_cuda else torch.float32,
        low_cpu_mem_usage=not has_cuda,
        trust_remote_code=False
    )

    _model.eval()
    _loaded_model_path = model_path

    print("✅ Model và tokenizer đã sẵn sàng.")
    return _model, _tokenizer
