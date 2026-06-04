import os
from google import genai

PROJECT_ID = "gcp-sandbox-kwlee"
LOCATION = "us-central1"
ENGINE_NAME = "projects/458778613248/locations/us-central1/reasoningEngines/1791159966984306688"

print("Initializing google-genai Client...")
# v1beta1 API 버전을 명시하여 Agent Platform/Reasoning Engine 호출 지원
client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION, http_options={'api_version': 'v1beta1'})

try:
    question = "GKE ob_log 데이터셋의 테이블들에서 오늘 발생한 시간별 에러 로그 빈도를 분석하고 차트로 그려줘."
    print(f"Sending Query to reasoningEngine: {ENGINE_NAME}")
    print(f"Question: '{question}'")
    
    response = client.models.generate_content(
        model=ENGINE_NAME,
        contents=question,
    )
    
    print("\n================== DEPLOYED AGENT RESPONSE ==================")
    print(response.text)
    print("=============================================================\n")

except Exception as e:
    print(f"\nERROR running remote genai test: {e}")
    import traceback
    traceback.print_exc()
