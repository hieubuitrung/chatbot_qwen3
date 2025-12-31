from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from llm.orchestrator import Orchestrator
from llm.agent import FunctionAgent
from llm.state import StateManager

app = FastAPI()
agent = FunctionAgent()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # hoặc ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],      # QUAN TRỌNG: cho OPTIONS
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    conversation_id: str
    message: str

@app.post("/chat")
def chat_stream(req: ChatRequest):

    def token_generator():
        orc = Orchestrator(req.conversation_id, agent)

        for token in orc.build_user_answer(req.message):
            # TRẢ VỀ TEXT THUẦN
            yield token

    return StreamingResponse(
        token_generator(),
        media_type="text/plain; charset=utf-8"
    )

class StopRequest(BaseModel):
    conversation_id: str

@app.post("/stop")
def stop_generation(req: StopRequest):
    state_manager = StateManager(req.conversation_id)
    state_manager.stop()
    return {
        "status": "ok",
        "message": "Generation stopped"
    }

@app.get("/chat/history")
def get_history(conversation_id: str, limit: int = 20):
    state_manager = StateManager(conversation_id)
    history = state_manager.get_chat_history(
        limit=limit
    )

    return {
        "conversation_id": conversation_id,
        "messages": history
    }