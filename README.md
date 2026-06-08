# GKE Conversational Log Analytics Agent

구글 **ADK (Agent Development Kit)**를 사용하여 GKE 로그 데이터베이스(BigQuery)를 분석하고, SRE 관점의 근본 원인 분석(RCA) 및 조치 가이드를 제공하는 대화형 인공지능 에이전트입니다.

---

## ⚙️ 주요 기능

- **BigQuery 테이블 동적 탐색**: 하드코딩된 단일 테이블 대신 구동 시점의 BigQuery 데이터셋 내 모든 테이블(예: `stdout_*`, `stderr_*`, `kubelet_*` 등)을 실시간으로 스캔하여 에이전트의 분석 범위로 등록합니다.
- **Cloud Logging GKE 내보내기 필터 학습**: GKE 로그 수집 규칙(online-boutique 클러스터 조건 및 node, pod, container, control plane component 리소스 필터 규칙)을 시스템 지침으로 탑재해 로그 정보와 인프라 정합성 이해도를 극대화했습니다.
- **차트 자동 렌더링**: 시간별 로그/에러 분포 등 시각화가 필요한 질문 시 Conversational Analytics API가 전달하는 Vega-Lite 명세를 캐치하여 로컬 이미지(`visualization.png`)로 렌더링 후 마크다운에 자동 임베딩합니다.
- **SRE 원인 분석 및 가이드 제공**: 복잡한 SQL 코드는 생략하고, 에러의 근본 원인 및 즉각 실행 가능한 `kubectl` 조치 가이드를 일목요연하게 작성하여 제공합니다.

---

## 🛠️ 개발 및 배포 환경 준비

### 1. 서비스 계정(SA) 생성 및 권한 설정
에이전트가 배포되어 가동될 때 Vertex AI 모델 및 BigQuery 로그 데이터베이스에 안전하게 접근할 수 있도록 전용 서비스 계정을 생성하고 권한을 바인딩합니다.

```bash
# 프로젝트 ID 설정
export PROJECT_ID=$(gcloud config get-value project)
export SA_EMAIL="google-cloud-ops-agent-sa@${PROJECT_ID}.iam.gserviceaccount.com"

# 1) 서비스 계정 생성
gcloud iam service-accounts create google-cloud-ops-agent-sa \
    --description="GKE Conversational Log Analytics Agent Service Account" \
    --display-name="GKE Log Analytics Agent SA"

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
GCP_RESOURCES_LOCATION="us-central1"

# BigQuery Log Resources
DATASET_ID="YOUR_BIGQUERY_DATASET_ID"               # GKE 로그가 있는 BigQuery 데이터셋 ID (예: ob_log)

# Telemetry & ADK Config
GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=true
GOOGLE_GENAI_USE_VERTEXAI=true
OTEL_SEMCONV_STABILITY_OPT_IN="gen_ai_latest_experimental"
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=EVENT_ONLY
```


### 2. 가상환경 및 패키지 설치
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

작성된 에이전트가 로컬 환경에서 올바르게 BigQuery 테이블을 동적으로 스캔하고 답변하는지 확인하려면 아래 ADK CLI 명령어를 사용해 대화형(Interactive) 모드로 실행하거나 단일 질문을 실행합니다.

```bash
# 1) 대화형(Interactive) 실행 모드 진입
uv run adk run .

# 2) 단일 질문으로 직접 검증 실행
uv run adk run . "최근 발생한 에러 로그의 원인이 뭐야? 시각화 차트도 함께 그려줘."
```

---

## 🚀 Agent Runtime (Vertex AI Reasoning Engine) 배포

에이전트를 구글 클라우드의 **Vertex AI Reasoning Engine (Agent Runtime)**에 배포하여 운영 환경에 적용합니다.

```bash
# 가상환경 활성화 (필요 시)
source .venv/bin/activate

# 플랫폼 배포 스크립트 실행
uv run python agent_platform/agent_runtime.py
```

배포가 성공적으로 완료되면 Vertex AI Reasoning Engine ID와 엔드포인트 정보가 터미널에 출력되며, Google Cloud Console의 Vertex AI Reasoning Engine 페이지에서 배포된 에이전트의 헬스체크 및 버전을 확인할 수 있습니다.
