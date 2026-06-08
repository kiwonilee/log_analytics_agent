import os
from google.genai import types

from google.adk.agents import Agent
from google.adk.models import Gemini
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.adk.tools import FunctionTool
from google.adk.apps import App

# Monkeypatch google-adk session validation to support Gemini Enterprise session IDs (which contain slashes)
try:
    import google.adk.sessions.vertex_ai_session_service as vertex_session_service
    vertex_session_service._validate_session_id = lambda session_id: None
    print("Successfully monkeypatched google-adk session ID validation.")
except Exception as patch_err:
    print(f"Note: google-adk session ID validation monkeypatch skipped: {patch_err}")

# 1. Conversational Analytics API 기반 로그 분석 도구 정의
from .conversational_analytics import query_with_conversational_analytics
query_with_conversational_analytics_tool = FunctionTool(query_with_conversational_analytics)

# 2. ADK 에이전트 세션 종료 시 대화 이력 메모리 관리 콜백 정의
async def generate_memories_callback(callback_context: CallbackContext):    
    """대화가 종료된 시점에 에이전트의 대화 이력을 메모리에 영구 저장하여 세션 간 컨텍스트를 유지합니다."""
    try:
        await callback_context.add_session_to_memory()
    except Exception as e:
        print(f"Warning: Could not add session to memory: {e}")

# 3. 외부 파일로부터 System Instruction 로드
current_dir = os.path.dirname(os.path.abspath(__file__))
system_instruction_path = os.path.join(current_dir, "agent_instruction.txt")
with open(system_instruction_path, "r", encoding="utf-8") as f:
    SYSTEM_INSTRUCTION = f.read()

# 4. 루트 에이전트 및 ADK App 조립
root_agent = Agent(
    name="log_analytics_agent",
    model=Gemini(
        model="gemini-3.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=SYSTEM_INSTRUCTION,
    tools=[query_with_conversational_analytics_tool, PreloadMemoryTool()],
    after_agent_callback=generate_memories_callback,
)

app = App(
    name="log_analytics_agent",
    root_agent=root_agent,
)

