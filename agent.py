import os
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.adk.tools import FunctionTool
from google.adk.apps import App
from google.genai import types
from google.cloud import geminidataanalytics

# 1. Load Configurations from Environment Variables
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT") or "gcp-sandbox-kwlee"
DATASET_ID = os.environ.get("DATASET_ID", "ob_log")

LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")

# GCS upload helper function for charts
def upload_to_gcs_and_get_url(local_file_path: str, blob_name: str) -> str:
    """로컬 파일을 GCS 버킷에 업로드하고, 15분간 유효한 Signed URL을 생성하여 반환합니다.
    Signed URL 생성 실패 시 보안 설정에 따라 Public-Read 권한 부여 후 일반 URL로 폴백합니다.
    """
    from google.cloud import storage
    import datetime
    import google.auth

    artifact_uri = os.environ.get("ADK_ARTIFACT_SERVICE_URI", "gs://adk-sandbox-bucket")
    bucket_name = artifact_uri.replace("gs://", "").split("/")[0]

    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        # 1. 파일 업로드
        blob.upload_from_filename(local_file_path, content_type="image/png")

        # 2. 서비스 계정 이메일 직접 구성 (v4 서명 시 메타데이터 환경 및 자격 증명 요구 대응)
        # 배포에 사용되는 서비스 계정은 'google-cloud-ops-agent-sa' 형식을 따르므로 프로젝트 ID를 활용해 직접 빌드합니다.
        service_account_email = f"google-cloud-ops-agent-sa@{PROJECT_ID}.iam.gserviceaccount.com"
        print(f"GCS Signed URL generation target SA: {service_account_email}")

        # 3. Signed URL 생성 시도
        try:
            url = blob.generate_signed_url(
                version="v4",
                expiration=datetime.timedelta(minutes=15),
                method="GET",
                service_account_email=service_account_email,
            )
            return url
        except Exception as sign_err:
            print(f"Warning: Signed URL generation failed, attempting public read fallback: {sign_err}")
            
            # GCS 서명 실패 시, 최종 폴백으로 해당 이미지만 임시로 읽기 권한을 해제하여 노출을 보장합니다.
            try:
                blob.make_public()
                return f"https://storage.googleapis.com/{bucket_name}/{blob_name}"
            except Exception as pub_err:
                print(f"Warning: Failed to make blob public as fallback: {pub_err}")
                return f"https://storage.googleapis.com/{bucket_name}/{blob_name}"
    except Exception as upload_err:
        print(f"Error uploading to GCS: {upload_err}")
        raise upload_err


# 2. Get or Create Conversational Analytics Data Agent helper
def get_or_create_data_agent(client, parent, display_name):
    try:
        # Search for existing agent with this display name
        list_req = geminidataanalytics.ListDataAgentsRequest(parent=parent)
        for agent in client.list_data_agents(request=list_req):
            if agent.display_name == display_name:
                return agent
    except Exception as e:
        print(f"Warning: Listing data agents failed: {e}")

    # Create new agent if not found
    from google.cloud import bigquery
    bq_client = bigquery.Client(project=PROJECT_ID)
    dataset_ref = bq_client.dataset(DATASET_ID)
    tables = bq_client.list_tables(dataset_ref)
    
    table_references = []
    for t in tables:
        table_ref = geminidataanalytics.BigQueryTableReference()
        table_ref.project_id = PROJECT_ID
        table_ref.dataset_id = DATASET_ID
        table_ref.table_id = t.table_id
        
        table_ref.schema = geminidataanalytics.Schema()
        table_ref.schema.description = f"Log table {t.table_id} in GKE ob_log dataset."
        table_references.append(table_ref)

    if not table_references:
        raise ValueError(f"No tables found in BigQuery dataset '{PROJECT_ID}.{DATASET_ID}'")

    published_context = geminidataanalytics.Context()
    published_context.datasource_references = geminidataanalytics.DatasourceReferences(
        bq=geminidataanalytics.BigQueryTableReferences(table_references=table_references)
    )
    published_context.system_instruction = (
        "You are GKE log analysis expert. Analyze logs in GKE tables. "
        f"Available tables are in dataset `{PROJECT_ID}.{DATASET_ID}`. "
        "These tables contain GKE logs exported from Cloud Logging with the following filter criteria:\n"
        f"- Project ID: {PROJECT_ID}\n"
        "- Cluster Name/ID: 'online-boutique'\n"
        "- Supported Resource Types: gke_cluster, gke_nodepool, k8s_cluster, k8s_node, k8s_pod, k8s_container, k8s_control_plane_component\n"
        "- Supported API Services: k8s.io, container.googleapis.com\n"
        "Use this context to accurately parse log sources and query GKE logs."
    )

    data_agent = geminidataanalytics.DataAgent()
    data_agent.display_name = display_name
    data_agent.description = f"Agent to analyze GKE logs in all tables of {PROJECT_ID}.{DATASET_ID}"
    data_agent.data_analytics_agent.published_context = published_context

    create_request = geminidataanalytics.CreateDataAgentRequest(
        parent=parent,
        data_agent=data_agent,
    )
    operation = client.create_data_agent(request=create_request)
    return operation.result()

# 3. Define the Conversational Analytics API Tool
def query_with_conversational_analytics(question: str) -> str:
    """Conversational Analytics API를 활용하여 자연어 질문으로 GKE 로그 데이터를 분석하고 결과를 반환합니다.
    
    Args:
        question: 분석할 자연어 질문 (예: "오늘 발생한 에러 로그의 개수는?")
    """
    try:
        agent_client = geminidataanalytics.DataAgentServiceClient()
        chat_client = geminidataanalytics.DataChatServiceClient()
        
        parent = f"projects/{PROJECT_ID}/locations/{LOCATION}"
        display_name = "GKE Advanced Log Agent"
        
        # 1. Get or Create Agent
        data_agent = get_or_create_data_agent(agent_client, parent, display_name)
        
        # 2. Create/Get Conversation Session
        conv_id = "gke-log-analytics-session"
        conversation = geminidataanalytics.Conversation(
            agents=[data_agent.name]
        )
        conv_request = geminidataanalytics.CreateConversationRequest(
            parent=parent,
            conversation_id=conv_id,
            conversation=conversation,
        )
        try:
            chat_client.create_conversation(request=conv_request)
        except Exception:
            pass # Ignore if conversation session already exists
            
        # 3. Chat with Agent
        chat_req = geminidataanalytics.ChatRequest(
            parent=parent,
            messages=[
                geminidataanalytics.Message(
                    user_message=geminidataanalytics.UserMessage(text=question)
                )
            ],
            conversation_reference=geminidataanalytics.ConversationReference(
                conversation=f"{parent}/conversations/{conv_id}"
            ),
            data_agent_context=geminidataanalytics.DataAgentContext(
                data_agent=data_agent.name
            )
        )
        
        stream = chat_client.chat(request=chat_req)
        final_response_parts = []
        vega_config = None
        
        for response in stream:
            if response.system_message:
                sys_msg = response.system_message
                if sys_msg.text:
                    text_msg = sys_msg.text
                    if text_msg.text_type == geminidataanalytics.TextMessage.TextType.FINAL_RESPONSE:
                        final_response_parts.extend(text_msg.parts)
                if sys_msg.chart and sys_msg.chart.result and sys_msg.chart.result.vega_config:
                    try:
                        chart_result_dict = geminidataanalytics.ChartResult.to_dict(sys_msg.chart.result)
                        vega_config = chart_result_dict.get("vega_config")
                    except Exception as parse_err:
                        pass
        
        answer = "".join(final_response_parts)
        
        if vega_config:
            try:
                import altair as alt
                chart = alt.Chart.from_dict(vega_config)
                image_path = "/tmp/visualization.png"
                chart.save(image_path)
                
                # GCS 버킷에 차트를 업로드하고 URL을 획득합니다.
                chart_url = upload_to_gcs_and_get_url(image_path, "charts/visualization.png")
                
                answer += (
                    f"\n\n#### 📊 GKE 로그 시각화 차트\n"
                    f"![GKE Log Visualization]({chart_url})\n"
                )
            except Exception as chart_err:
                answer += f"\n\n*(차트 렌더링 및 GCS 업로드 중 오류 발생: {chart_err})*\n"
                
        return (
            f"### [Conversational Analytics API 방식 결과 요약]\n"
            f"{answer}\n"
        )
    except Exception as e:
        return f"### [Conversational Analytics API 방식 결과 요약]\n- **오류 발생**: {str(e)}\n"

query_with_conversational_analytics_tool = FunctionTool(query_with_conversational_analytics)

# 4. Define Memory callback
async def generate_memories_callback(callback_context: CallbackContext):    
    try:
        await callback_context.add_session_to_memory()
    except Exception as e:
        print(f"Warning: Could not add session to memory: {e}")
    return None

# 5. Define System Instruction and root Agent
SYSTEM_INSTRUCTION = (
    "페르소나: 'GKE 및 Kubernetes 전문 아키텍트/운영 네비게이터'\n\n"
    
    "역할 및 목적:\n"
    "운영자가 자연어로 GKE 로그 분석, 에러 원인 추적, Pod 상태 점검 등을 질문하면, "
    "반드시 `query_with_conversational_analytics` 도구를 호출하는 'Conversational Analytics API 방식'을 실행하여 결과를 도출하고, "
    "SRE 운영 관점에서 정밀한 원인 분석 및 조치 가이드를 제공해야 합니다. "
    "사용자는 실제 생성된 SQL 쿼리에는 관심이 없으므로, 생성한 SQL 쿼리문은 출력에서 일체 제외해 주세요.\n\n"

    "핵심 분석 분야 및 진단 가이드:\n"
    "에이전트는 다음 4가지 핵심 GKE 운영 및 트러블슈팅 분야에 대해 전문적인 분석 가이드를 제시해야 합니다:\n"
    "1. **장애 탐지 및 근본 원인 분석 (RCA)**:\n"
    "   - 특정 서비스/네임스페이스의 에러 로그 발생 빈도를 분석하여 가장 높은 비율의 에러 유형과 구체적인 해결책을 제시합니다.\n"
    "   - Pod 재시작(Restart) 감지 시, 재시작 발생 직전 5분간의 로그(stdout/stderr)를 추적 및 매핑 분석하여 다운 원인(예: OOM, SIGTERM, App crash, Exception)을 진단합니다.\n"
    "   - API Gateway 5xx 에러 등 장애 급증 시, trace_id 등 고유 식별자나 타임스탬프를 매핑하여 백엔드 마이크로서비스 간의 지연 및 실패 타임라인을 작성합니다.\n"
    "2. **리소스 및 인프라 이상 징후 분석**:\n"
    "   - OOMKilled(Out of Memory) 현상(exit code 137)을 감지하고, 비정상 종료된 파드 목록과 메모리 누수(Memory Leak)가 의심되는 로그 패턴(예: heap memory exhaustion)을 분석합니다.\n"
    "   - GKE 노드 상태 이상(NotReady, DiskPressure 등)이 감지되면 Kubelet 및 시스템 로그를 검사하여 노드 과부하 및 디스크 압박의 원인을 진단합니다.\n"
    "3. **배포 및 변경 사항 영향도 검증**:\n"
    "   - 신규 배포(Rolling Update 등) 직후 30분간의 로그를 이전 버전과 비교 대조하여, 새 버전에서만 새롭게 관찰되는 Warning/Error 로그 패턴을 도출합니다.\n"
    "   - 특정 컨테이너 이미지 버전 적용 이후 발생하는 CrashLoopBackOff 및 Liveness/Readiness Probe 실패 로그를 검출해 복구 가이드를 제공합니다.\n"
    "4. **보안 및 감사(Audit) 로그 분석**:\n"
    "   - Kubernetes 감사 로그(cloudaudit) 테이블을 조회하여 403 Forbidden(권한 거부)이 대량 발생한 API 요청의 대상 리소스 및 ServiceAccount/User 정보를 식별합니다.\n"
    "   - 내부망이 아닌 외부 공인 IP에서 kube-apiserver로 접근한 비정상 기록이나 cluster-admin과 같은 핵심 권한 변경 사항을 추적 보고합니다.\n\n"

    "출력 양식:\n"
    "답변은 친절하고 전문적인 한국어(Korean)로 작성하며, 아래와 같은 Markdown 형태로 작성하세요. "
    "SQL 쿼리문은 포함하지 말아야 합니다:\n\n"
    "### 1. Conversational Analytics API 방식 결과 요약\n"
    "- [Conversational Analytics API가 반환한 내용 중 요약 및 인사이트 텍스트만 표시]\n"
    "- [시간별 동향 분석 등 차트 데이터가 존재할 경우 아래 마크다운 포맷으로 차트 이미지를 본문에 포함합니다]\n"
    "  #### 📊 GKE 로그 시각화 차트\n"
    "  ![GKE Log Visualization](https://storage.googleapis.com/<bucket_name>/charts/visualization.png?signed_parameters)\n\n"
    "### 2. SRE 원인 분석 및 GKE 운영자 조치 가이드\n"
    "- **장애/에러 원인 진단**: 발견된 에러 로그의 구체적인 기술적 원인, 리소스 압박, 배포 변경의 영향 혹은 보안 위협을 다각도로 매핑하여 진단합니다.\n"
    "- **GKE 운영자 조치 가이드 (Next Actions)**: 운영자가 장애 복구 또는 검증을 위해 즉각 취해야 할 행동지침 및 kubectl 명령어 예시를 구체적으로 작성하세요."
)

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
