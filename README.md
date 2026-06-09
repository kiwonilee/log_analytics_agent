# Cloud Conversational Log Analytics Agent (AIOps Agent)

구글 **ADK (Agent Development Kit)**와 구글 클라우드의 **Conversational Analytics API (Gemini Data Analytics)**를 사용하여 Google Cloud 환경의 대규모 서비스 로그(BigQuery)를 분석하고, SRE/DevOps 관점의 문제 진단, 원인 분석(RCA), 조치 가이드를 제공하는 대화형 인공지능 AIOps 에이전트입니다.

이 에이전트는 Google Cloud의 Cloud Logging 등을 통해 BigQuery로 내보내기(Export)된 다양한 인프라/애플리케이션 로그 데이터를 분석 대상으로 삼으며, Conversational Analytics API의 강력한 자연어-SQL 변환 및 요약 능력을 활용하여 운영자가 SQL 쿼리를 모르더라도 자연어 대화만으로 복잡한 실시간 로그 분석 및 운영 관제(AIOps) 업무를 수행할 수 있도록 돕습니다.

---

## ⚙️ 주요 기능

- **Conversational Analytics API 기반 자연어 분석**: 대량의 로그 테이블을 직접 SQL로 쿼리하는 대신, Conversational Analytics API를 백엔드로 활용해 자연어 질문을 최적의 BigQuery SQL로 자동 번역 및 실행하여 로그 분석 결과를 요약하여 가져옵니다.
- **동적 로그 맥락 학습 (Session Memory)**: 시작 시 사용자가 분석하고자 하는 로그 종류와 수집 맥락 정보(예: Cloud Run 앱 로그, Nginx 서버 로그, GKE 클러스터 감사 로그 등)를 대화 세션 메모리에 동적으로 저장하고 이후 분석 시 계속해서 참조합니다.
- **BigQuery 데이터셋 동적 스캔**: 하드코딩된 단일 테이블 스캔 대신, 연결된 BigQuery 데이터셋 내 모든 관련 테이블 구조를 실시간으로 탐색하여 대화 맥락에 맞는 대상을 매핑합니다.
- **SRE 관점의 구조화된 분석**: 복잡한 SQL 코드는 요약하고, 장애 원인 분석(RCA), 리소스 및 인프라 상태 이상 탐지, 배포 변경 영향도 검증, 보안 및 감사 로그 분석 가이드를 마크다운 표 및 단계별 명령어 템플릿으로 제공합니다.

---

## 🛠️ 개발 및 배포 환경 준비

### 1. 환경변수 설정
아래 환경변수들을 먼저 터미널에 내보내기(export)하여 이후 설정 과정을 원활하게 진행합니다.
```bash
# 프로젝트 ID 설정
export PROJECT_ID="YOUR_GOOGLE_CLOUD_PROJECT_ID"

# Agent Runtime 및 리소스를 배포할 Region (예: us-central1)
export RESOURCE_LOCATION="us-central1"

# 에이전트 구동 및 배포에 사용할 Service Account 이메일 ("agent-sa@${PROJECT_ID}.iam.gserviceaccount.com")
export SA_EMAIL="SA_EMBAIL"

# 로그를 저장할 BigQuery 데이터셋 이름 (예: logs)
export BQ_DATASET_ID="YOUR_BIGQUERY_DATASET_ID"

# 배포 staging 및 아티팩트 저장을 위한 GCS 버킷 이름 (gs://log-analytics-bucket-${PROJECT_ID})
export BUCKET_NAME="gs://xxxx"
```

```bash
echo $PROJECT_ID
echo $RESOURCE_LOCATION
echo $SA_EMAIL
echo $BQ_DATASET_ID
echo $BUCKET_NAME
```

## 🚀 [사전작업] BigQuery 로그 데이터셋 및 수집 설정 (선택/예시)
운영 로그가 저장될 BigQuery 데이터셋을 생성하고, Cloud Logging의 로그를 실시간으로 BigQuery에 동기화하기 위한 로그 싱크(Sink)를 설정합니다.

```bash
# 1) BigQuery 데이터셋 생성
bq --project_id=${PROJECT_ID} mk \
  --location=${RESOURCE_LOCATION} \
  --description="Cloud Logging" \
  ${BQ_DATASET_ID}

# 2) Cloud Logging 의 모든 로그 BigQuery 로 내보내기(Log Sink) 설정
gcloud logging sinks create cloud_logs_export_sink \
  bigquery.googleapis.com/projects/${PROJECT_ID}/datasets/${BQ_DATASET} \
  --log-filter="" \
  --project=${PROJECT_ID}
```

### 2. GCS 버킷 생성 (배포 및 아티팩트 저장용)
에이전트 코드 아카이빙과 실행 중 임시 아티팩트 저장을 위해 GCS 버킷을 생성합니다.
```bash
gcloud storage buckets create ${BUCKET_NAME} --location=${RESOURCE_LOCATION}
```

### 4. Cloud Log Analytics Agent 코드 체크아웃
```bash
git clone https://github.com/kiwonilee/log_analytics_agent.git
cd log_analytics_agent
```

### 3. 환경 변수 파일 생성 및 연동
`.env.template`을 바탕으로 에이전트 런타임 환경 설정 파일(`.env`)을 생성하고 프로젝트 변수값을 치환합니다.
```bash
cp .env.template .env

# 변수값 자동 업데이트
sed -i "s/YOUR_GOOGLE_CLOUD_PROJECT_ID/${PROJECT_ID}/g" .env
sed -i "s/YOUR_GCP_RESOURCE_LOCATION/${RESOURCE_LOCATION}/g" .env
sed -i "s/YOUR_BIGQUERY_DATASET_ID/${BQ_DATASET}/g" .env
```

### 4. 서비스 계정(SA) 생성 및 권한 설정
에이전트가 배포되어 가동될 때 Vertex AI 모델 및 BigQuery 로그 데이터베이스에 안전하게 접근할 수 있도록 전용 서비스 계정을 생성하고 권한을 바인딩합니다.

```bash
# 1) 서비스 계정 생성
gcloud iam service-accounts create agent-sa \
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

### 5. 가상환경 및 패키지 설치
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
uv run adk run . "최근 발생한 에러 로그의 원인이 뭐야?"
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


