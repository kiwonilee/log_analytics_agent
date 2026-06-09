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

## 📂 프로젝트 폴더 및 파일 구성

- **[agent.py](agent.py)**: ADK 에이전트 엔트리포인트로, 도구 및 시스템 지침 바인딩과 대화 세션 관리 역할을 수행합니다.
- **[agent_instruction.txt](agent_instruction.txt)**: 에이전트 가이드라인 및 SRE 관점의 출력 형식(Incident 대시보드, 리포트 템플릿 등)을 명시한 시스템 지침서입니다.
- **[conversational_analytics.py](conversational_analytics.py)**: 구글 클라우드의 Conversational Analytics API를 활용하여 자연어 기반의 BigQuery 로그 데이터 스캔 및 분석 작업을 처리하는 커스텀 도구입니다.
- **[agent_platform/agent_runtime.py](agent_platform/agent_runtime.py)**: 배포 스크립트로, 로컬/터미널 환경변수 유효성을 엄격하게 사전 검증하고 Vertex AI Reasoning Engine에 에이전트를 원클릭 배포합니다.
- **[.env.template](.env.template)**: 프로젝트 환경 변수 설정 정보 파일의 가이드라인 템플릿입니다.

---

## 🛠️ 개발 및 배포 환경 준비

### 1. Cloud Log Analytics Agent 코드 체크아웃
```bash
git clone https://github.com/kiwonilee/log_analytics_agent.git
cd log_analytics_agent
```

### 2. 환경변수 설정
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

## 🚀 [선택 사전작업] BigQuery 로그 데이터셋 및 수집 설정 (선택/예시)
운영 로그가 저장될 BigQuery 데이터셋을 생성하고, Cloud Logging의 로그를 실시간으로 BigQuery에 동기화하기 위한 로그 싱크(Sink)를 설정합니다.

```bash
# 1) GKE 클러스터 생성
gcloud container clusters create-auto ob-cluster --region us-central1

gcloud container clusters get-credentials ob-cluster --location us-central1

# 2) GKE 클러스터에 워크로드 배포
kubectl apply -f https://raw.githubusercontent.com/GoogleCloudPlatform/microservices-demo/main/release/kubernetes-manifests.yaml

# 3) BigQuery 데이터셋 생성
bq --project_id=${PROJECT_ID} mk \
  --location=${RESOURCE_LOCATION} \
  --description="Cloud Logging" \
  ${BQ_DATASET_ID}

# 4) Cloud Logging 의 모든 로그 BigQuery 로 내보내기(Log Sink) 설정
gcloud logging sinks create cloud_logs_export_sink \
  bigquery.googleapis.com/projects/${PROJECT_ID}/datasets/${BQ_DATASET} \
  --log-filter="" \
  --project=${PROJECT_ID}

# 5) BigQuery 의 Write 할 수 있는 권한 부여
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
--member=$(gcloud logging sinks describe cloud_logs_export_sink --format="value(writerIdentity)") \
  --role="roles/bigquery.dataEditor"

```

### 3. GCS 버킷 생성 (배포 및 아티팩트 저장용)
에이전트 코드 아카이빙과 실행 중 임시 아티팩트 저장을 위해 GCS 버킷을 생성합니다.
```bash
gcloud storage buckets create ${BUCKET_NAME} --location=${RESOURCE_LOCATION}
```


### 4. 환경 변수 파일 생성 및 연동
`.env.template`을 바탕으로 에이전트 런타임 환경 설정 파일(`.env`)을 생성하고 프로젝트 변수값을 치환합니다.
```bash
cp .env.template .env

# 변수값 자동 업데이트
sed -i "s/YOUR_GOOGLE_CLOUD_PROJECT_ID/${PROJECT_ID}/g" .env
sed -i "s/YOUR_GCP_RESOURCE_LOCATION/${RESOURCE_LOCATION}/g" .env
sed -i "s/YOUR_BIGQUERY_DATASET_ID/${BQ_DATASET}/g" .env
```

### 5. 서비스 계정(SA) 생성 및 권한 설정
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
    monitoring.googleapis.com \
    aiplatform.googleapis.com \
    geminidataanalytics.googleapis.com \
    apphub.googleapis.com
```

---

## 🚀 Agent Runtime (Vertex AI Reasoning Engine) 배포

에이전트를 구글 클라우드의 **Vertex AI Reasoning Engine (Agent Runtime)**에 배포하여 운영 환경(Gemini Enterprise 등)에 배포 및 연결합니다.

```bash
# 플랫폼 배포 스크립트 실행
uv run python agent_platform/agent_runtime.py
```

배포가 성공적으로 완료되면 배포된 에이전트의 Resource Name(예: `projects/.../locations/global/reasoningEngines/...`) 정보가 출력되며, Google Cloud Console의 Vertex AI Reasoning Engine 대시보드에서 헬스 체크 및 버전 상태를 관리할 수 있습니다.


## 🚀 Agent Runtime에 배포한 Agent를 Gemini Enterprise App에 등록하기

Vertex AI Agent Engine(Agent Runtime)에 배포가 완료된 커스텀 에이전트를 Gemini Enterprise(구 Google Cloud console 내 Gemini) 대시보드에 연결하여 대화형 인터페이스에서 사용하기 위한 절차입니다. 자세한 매뉴얼은 [공식 문서](https://docs.cloud.google.com/gemini/enterprise/docs/register-and-manage-an-adk-agent)를 참고하십시오.

### 1단계: OAuth 클라이언트 ID 생성 (에이전트 권한 부여)
Gemini Enterprise가 사용자를 대신하여 배포된 Agent Runtime API를 호출할 수 있도록 OAuth 2.0 클라이언트를 생성합니다.
1. GCP 콘솔의 **APIs & Services > Credentials** 페이지로 이동합니다.
2. **+ Create Credentials**를 클릭하고 **OAuth client ID**를 선택합니다.
3. **Application type**을 `Web application`으로 설정합니다.
4. **Name**에 클라이언트 이름(예: `ge-agent-app`)을 입력합니다.
5. [공식 문서 가이드 (Authorize your agent)](https://docs.cloud.google.com/gemini/enterprise/docs/register-and-manage-an-adk-agent#authorize-your-agent)를 확인하여 승인된 리디렉션 URI(Authorized redirect URIs)를 입력합니다.
6. **Create**를 클릭한 후, 생성된 클라이언트 정보 창에서 **Download JSON**을 눌러 JSON 키 파일을 로컬에 다운로드합니다.

### 2단계: Gemini Enterprise에 커스텀 에이전트 등록
1. **Gemini Enterprise** 콘솔 화면에 진입합니다.
2. 좌측 메뉴에서 **Agent**를 클릭한 후 **Add agent**를 선택합니다.
3. 등록 유형으로 **Custom agent via Agent Runtime**을 클릭합니다.
4. 배포 단계에서 획득한 에이전트 리소스 명(예: `projects/.../locations/global/reasoningEngines/...`)을 입력하여 연결합니다.
5. [공식 문서 가이드 (Register an ADK agent)](https://docs.cloud.google.com/gemini/enterprise/docs/register-and-manage-an-adk-agent#register-an-adk-agent)의 안내에 따라 에이전트 등록 세부 정보를 입력합니다.

### 3단계: 인증(Authorizations) 추가 및 연결
1. 등록된 에이전트의 상세 화면에서 **Authorizations** 섹션으로 이동하여 **Add authorization**을 누릅니다.
2. 1단계에서 다운로드했던 OAuth 클라이언트 JSON 키 정보를 사용하여 연동 인증을 최종 활성화합니다.

---

## 💻 로컬 검증 및 실행 방법

작성된 에이전트가 로컬 환경에서 올바르게 작동하는지 확인하려면 아래 ADK CLI 명령어를 사용해 대화형(Interactive) 모드로 가동해 보실 수 있습니다.
`uv` 패키지 매니저 또는 일반 가상환경을 사용하여 의존성을 설치합니다.

```bash
# 가상환경 생성 및 활성화
uv venv
source .venv/bin/activate

# 의존성 패키지 동기화
uv sync
```

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
