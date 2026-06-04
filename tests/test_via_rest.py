import sys
import json
from google.auth import default
from google.auth.transport.requests import AuthorizedSession

PROJECT_ID = "gcp-sandbox-kwlee"
LOCATION = "us-central1"
ENGINE_ID = "1791159966984306688"

# 1. Get default credentials and create an authorized session
credentials, project = default()
authed_session = AuthorizedSession(credentials)

# 2. Build REST endpoint URL for streamQuery
url = f"https://{LOCATION}-aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{ENGINE_ID}:streamQuery"

# payload matching the query structure expected by the agent
payload = {
    "input": {
        "message": "GKE ob_log 데이터셋의 테이블들에서 오늘 발생한 시간별 에러 로그 빈도를 분석하고 차트로 그려줘.",
        "user_id": "test-user-1"
    }
}

print(f"Sending REST API request to: {url}")
print(f"Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")

try:
    response = authed_session.post(url, json=payload, stream=True)
    print(f"Response Status Code: {response.status_code}")
    
    if response.status_code == 200:
        print("\n=== Streaming Response ===")
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                # Parse JSON if possible to show it nicely
                try:
                    data = json.loads(decoded_line)
                    # Pretty print the SSE data
                    print(json.dumps(data, ensure_ascii=False, indent=2))
                except Exception:
                    print(decoded_line)
        print("==========================\n")
    else:
        print(f"Error Response Body: {response.text}")
except Exception as e:
    print(f"Exception during request: {e}")
