# stopping.py
from transformers import StoppingCriteria

class StopByConversation(StoppingCriteria):
    def __init__(self, stop_flag: dict):
        self.stop_flag = stop_flag

    def __call__(self, input_ids, scores, **kwargs):
        return self.stop_flag.get("stop", False)
