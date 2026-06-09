# Cloud Conversational Log Analytics Agent (AIOps Agent)

구글 **ADK (Agent Development Kit)**와 구글 클라우드의 **Conversational Analytics API (Gemini Data Analytics)**를 사용하여 Google Cloud 환경의 대규모 서비스 로그(BigQuery)를 분석하고, SRE/DevOps 관점의 문제 진단, 원인 분석(RCA), 조치 가이드 및 시각화 차트를 제공하는 대화형 인공지능 AIOps 에이전트입니다.

이 에이전트는 Google Cloud의 Cloud Logging 등을 통해 BigQuery로 내보내기(Export)된 다양한 인프라/애플리케이션 로그 데이터를 분석 대상으로 삼으며, Conversational Analytics API의 강력한 자연어-SQL 변환 및 요약 능력을 활용하여 운영자가 SQL 쿼리를 모르더라도 자연어 대화만으로 복잡한 실시간 로그 분석 및 운영 관제(AIOps) 업무를 수행할 수 있도록 돕습니다.

---

## ⚙️ 주요 기능

- **Conversational Analytics API 기반 자연어 분석**: 대량의 로그 테이블을 직접 SQL로 쿼리하는 대신, Conversational Analytics API를 백엔드로 활용해 자연어 질문을 최적의 BigQuery SQL로 자동 번역 및 실행하여 분석 결과와 차트 스펙을 가져옵니다.
- **동적 로그 맥락 학습 (Session Memory)**: 시작 시 사용자가 분석하고자 하는 로그 종류와 수집 맥락 정보(예: Cloud Run 앱 로그, Nginx 서버 로그, GKE 클러스터 감사 로그 등)를 대화 세션 메모리에 동적으로 저장하고 이후 분석 시 계속해서 참조합니다.
- **BigQuery 데이터셋 동적 스캔**: 하드코딩된 단일 테이블 스캔 대신, 연결된 BigQuery 데이터셋 내 모든 관련 테이블 구조를 실시간으로 탐색하여 대화 맥락에 맞는 대상을 매핑합니다.
- **인터랙티브 차트 자동 렌더링**: 시간별 로그/에러 분포 추이 등 시각화 분석 질문 시, Conversational Analytics API가 전달하는 차트 명세를 캐치하여 응답 텍스트 내에 ```` ```vega-lite ```` 코드 블록으로 구조화된 Vega-Lite JSON 명세서를 인라인 데이터와 함께 출력합니다. Gemini Enterprise UI는 이를 감지하여 화면에 동적 대화형 차트를 자동으로 렌더링해 줍니다.
- **SRE 관점의 구조화된 분석**: 복잡한 SQL 코드는 요약하고, 장애 원인 분석(RCA), 리소스 및 인프라 상태 이상 탐지, 배포 변경 영향도 검증, 보안 및 감사 로그 분석 가이드를 마크다운 표 및 단계별 명령어 템플릿으로 제공합니다.

---

## 🛠️ 개발 및 배포 환경 준비

### 1. 서비스 계정(SA) 생성 및 권한 설정
에이전트가 배포되어 가동될 때 Vertex AI 모델 및 BigQuery 로그 데이터베이스에 안전하게 접근할 수 있도록 전용 서비스 계정을 생성하고 권한을 바인딩합니다.

```bash
# 프로젝트 ID 설정
export PROJECT_ID=$(gcloud config get-value project)
export SA_EMAIL="google-cloud-ops-agent-sa@${PROJECT_ID}.iam.gserviceaccount.com"
```

```bash
# 1) 서비스 계정 생성
gcloud iam service-accounts create google-cloud-ops-agent-sa \
    --description="Conversational Cloud Log Analytics Agent Service Account" \
    --display-name="Cloud Log Analytics Agent SA"

# 2) BigQuery 권한 부여 (로그 분석용)
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/bigquery.admin"

# 3) Vertex AI 권한 부여 (Gemini 모델 호출용)
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/aiplatform.user"

# 4) GCS staging bucket 권한 부여 (에이전트 패키지 아카이빙용)
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/storage.objectUser"

# 5) OpenTelemetry Traces & Logs 수집 권한 부여 (Telemetry 가시성 활성화용)
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/cloudtrace.agent"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/logging.logWriter"

# 6) 필수 API 활성화 (Cloud Trace & Telemetry API)
gcloud services enable \
    cloudtrace.googleapis.com \
    telemetry.googleapis.com \
    monitoring.googleapis.com
```

### 2. 환경 변수 설정

`log_analytics_agent/.env.template` 파일을 복사하여 `.env` 파일을 생성하고 필요한 설정 정보를 입력합니다.

```bash
# 템플릿 파일 복사
cp log_analytics_agent/.env.template log_analytics_agent/.env
```

`log_analytics_agent/.env` 파일을 편집기로 열어 프로젝트 정보와 리소스 식별자를 본인의 GCP 환경에 맞춰 작성합니다.

```ini
# Google Cloud Configuration
GOOGLE_CLOUD_PROJECT="YOUR_GOOGLE_CLOUD_PROJECT_ID" # 사용할 GCP 프로젝트 ID
GOOGLE_CLOUD_LOCATION="global"
GOOGLE_GENAI_USE_VERTEXAI=true

GCP_RESOURCES_LOCATION="us-central1"

# BigQuery Log Resources
DATASET_ID="YOUR_BIGQUERY_DATASET_ID"               # 로그가 적재된 BigQuery 데이터셋 ID (예: ob_log)

# Telemetry & ADK Config
GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=true
OTEL_SEMCONV_STABILITY_OPT_IN="gen_ai_latest_experimental"
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=EVENT_ONLY
```


### 3. 가상환경 및 패키지 설치
`uv` 패키지 매니저 또는 일반 가상환경을 사용하여 의존성을 설치합니다.
```bash
# 가상환경 생성 및 활성화
uv venv
source .venv/bin/activate

# 의존성 패키지 동기화
uv sync
```

---

## 💻 로컬 검증 및 실행 방법

작성된 에이전트가 로컬 환경에서 올바르게 작동하는지 확인하려면 아래 ADK CLI 명령어를 사용해 대화형(Interactive) 모드로 가동해 보실 수 있습니다.

```bash
# 1) 대화형(Interactive) 실행 모드 진입
uv run adk run .

# 2) 단일 질문으로 직접 검증 실행
uv run adk run . "최근 발생한 에러 로그의 원인이 뭐야? 시각화 차트도 함께 그려줘."
```

로컬 웹 테스트 서버를 띄워 UI 환경에서 시연을 원하신다면 다음 명령어를 사용합니다.
```bash
uv run adk web
```

---

## 🚀 Agent Runtime (Vertex AI Reasoning Engine) 배포

에이전트를 구글 클라우드의 **Vertex AI Reasoning Engine (Agent Runtime)**에 배포하여 운영 환경(Gemini Enterprise 등)에 배포 및 연결합니다.

```bash
# 플랫폼 배포 스크립트 실행
uv run python agent_platform/agent_runtime.py
```

배포가 성공적으로 완료되면 배포된 에이전트의 Resource Name(예: `projects/.../locations/global/reasoningEngines/...`) 정보가 출력되며, Google Cloud Console의 Vertex AI Reasoning Engine 대시보드에서 헬스 체크 및 버전 상태를 관리할 수 있습니다.
