import os
import uuid
import proto
from google.cloud import bigquery
from google.cloud import geminidataanalytics
from google.genai import types
from google.adk.tools import ToolContext
from google.protobuf.json_format import MessageToDict

# 1. Proto 변환 헬퍼 함수 정의
def _convert(v):
    """Proto 맵/리스트 복합 타입을 Altair에서 사용 가능한 파이썬 기본 dict/list 구조로 재귀 변환합니다."""
    if isinstance(v, proto.marshal.collections.maps.MapComposite):
        return {k: _convert(val) for k, val in v.items()}
    elif isinstance(v, proto.marshal.collections.RepeatedComposite):
        return [_convert(el) for el in v]
    elif isinstance(v, (int, float, str, bool, type(None))):
        return v
    else:
        return MessageToDict(v)

# 1. 환경 변수 기반 설정 정보 로드
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
DATASET_ID = os.environ.get("DATASET_ID")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")



def get_or_create_data_agent(client, parent, display_name, log_context):
    """지정된 디스플레이 이름의 DataAgent가 이미 있으면 이를 반환하고, 없으면 새로 생성합니다."""
    try:
        list_req = geminidataanalytics.ListDataAgentsRequest(parent=parent)
        for agent in client.list_data_agents(request=list_req):
            if agent.display_name == display_name:
                return agent
    except Exception as e:
        print(f"Warning: Listing data agents failed: {e}")

    # BigQuery 데이터셋 내부의 모든 로그 테이블 바인딩
    bq_client = bigquery.Client(project=PROJECT_ID)
    tables = bq_client.list_tables(bq_client.dataset(DATASET_ID))
    
    table_references = [
        geminidataanalytics.BigQueryTableReference(
            project_id=PROJECT_ID,
            dataset_id=DATASET_ID,
            table_id=t.table_id,
            schema=geminidataanalytics.Schema(description=f"Log table {t.table_id} containing {log_context} logs.")
        )
        for t in tables
    ]

    if not table_references:
        raise ValueError(f"No tables found in BigQuery dataset '{PROJECT_ID}.{DATASET_ID}'")

    system_instruction = (
        f"You are a log analysis expert. Analyze logs in the tables.\n"
        f"The user has specified that these tables contain: {log_context}.\n"
        f"Available tables are in dataset `{PROJECT_ID}.{DATASET_ID}`.\n"
        f"Use this context to accurately parse log sources and query logs."
    )

    published_context = geminidataanalytics.Context(
        datasource_references=geminidataanalytics.DatasourceReferences(
            bq=geminidataanalytics.BigQueryTableReferences(table_references=table_references)
        ),
        system_instruction=system_instruction
    )

    data_agent = geminidataanalytics.DataAgent(
        display_name=display_name,
        description=f"Agent to analyze logs ({log_context}) in all tables of {PROJECT_ID}.{DATASET_ID}"
    )
    data_agent.data_analytics_agent.published_context = published_context

    create_request = geminidataanalytics.CreateDataAgentRequest(parent=parent, data_agent=data_agent)
    return client.create_data_agent(request=create_request).result()

async def query_with_conversational_analytics(question: str, log_context: str, tool_context: ToolContext) -> str:
    """Conversational Analytics API를 활용하여 자연어 질문으로 로그 데이터를 분석하고 결과를 반환합니다.
    
    Args:
        question: 분석할 자연어 질문 (예: "오늘 발생한 에러 로그의 개수는?")
        log_context: 분석 대상 로그에 대한 수집 맥락 정보 (예: "Cloud Run 애플리케이션 로그", "Nginx 웹서버 로그")
    """
    try:
        agent_client = geminidataanalytics.DataAgentServiceClient()
        chat_client = geminidataanalytics.DataChatServiceClient()
        
        parent = f"projects/{PROJECT_ID}/locations/{LOCATION}"
        
        # Create a safe display name based on log_context
        import re
        safe_context = re.sub(r'[^a-zA-Z0-9\s\-]', '', log_context)[:40].strip()
        display_name = f"Log Agent - {safe_context}" if safe_context else "Generic Log Agent"
        
        data_agent = get_or_create_data_agent(agent_client, parent, display_name, log_context)
        
        # 고유 세션 ID 생성 및 일시 대화 세션 생성
        conv_id = f"log-session-{uuid.uuid4().hex}"
        conversation_name = f"{parent}/conversations/{conv_id}"
        
        conv_request = geminidataanalytics.CreateConversationRequest(
            parent=parent,
            conversation_id=conv_id,
            conversation=geminidataanalytics.Conversation(agents=[data_agent.name])
        )
        chat_client.create_conversation(request=conv_request)
            
        final_response_parts, vega_config = [], None
        
        try:
            chat_req = geminidataanalytics.ChatRequest(
                parent=parent,
                messages=[geminidataanalytics.Message(user_message=geminidataanalytics.UserMessage(text=question))],
                conversation_reference=geminidataanalytics.ConversationReference(
                    conversation=conversation_name,
                    data_agent_context=geminidataanalytics.DataAgentContext(data_agent=data_agent.name)
                )
            )
            
            stream = chat_client.chat(request=chat_req)
            
            for response in stream:
                sys_msg = response.system_message
                if not sys_msg:
                    continue
                
                # 최종 답변 텍스트 취합
                if sys_msg.text and sys_msg.text.text_type == geminidataanalytics.TextMessage.TextType.FINAL_RESPONSE:
                    final_response_parts.extend(sys_msg.text.parts)
                
                # 차트 설정 파일 파싱 (Proto 객체 상태로 직접 획득)
                if sys_msg.chart and sys_msg.chart.result and sys_msg.chart.result.vega_config:
                    vega_config = sys_msg.chart.result.vega_config
        finally:
            try:
                chat_client.delete_conversation(name=conversation_name)
            except Exception as delete_err:
                print(f"Warning: Failed to delete conversation {conversation_name}: {delete_err}")
        
        answer = "".join(final_response_parts)
        
        # 차트 존재 시 Vega-Lite JSON 스펙을 코드 블록으로 직접 출력
        if vega_config:
            try:
                import json
                vega_dict = _convert(vega_config)
                vega_json = json.dumps(vega_dict, indent=2)
                
                answer += f"\n\n### 📊 에러 로그 발생 동향 차트 (Vega-Lite)\n```json:vega\n{vega_json}\n```\n"
            except Exception as chart_err:
                answer += f"\n\n*(차트 데이터 변환 중 오류 발생: {chart_err})*\n"
                
        return f"### [Conversational Analytics API 방식 결과 요약]\n{answer}\n"
    except Exception as e:
        return f"### [Conversational Analytics API 방식 결과 요약]\n- **오류 발생**: {str(e)}\n"
