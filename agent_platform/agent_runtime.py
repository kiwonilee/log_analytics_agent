import os
import sys
from dotenv import load_dotenv
from vertexai.agent_engines import AdkApp

# Set up project path namespaces and change directory to parent to allow proper packaging
project_parent = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
os.chdir(project_parent)
if project_parent not in sys.path:
    sys.path.insert(0, project_parent)

# Load configurations from the project's .env file
load_dotenv(os.path.join(project_parent, "log_analytics_agent/.env"))

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("GCP_RESOURCES_LOCATION")

# Initialize client with v1beta1 support for Agent Identity
import vertexai
from vertexai import types as vertexai_types

client = vertexai.Client(
    project=PROJECT_ID,
    location=LOCATION,
    http_options=dict(api_version="v1beta1")
)

# Import and wrap the Log Analytics app via its package path
from log_analytics_agent.agent import app
adk_app = AdkApp(app=app)

# -----------------------------------------------------------------------------
# Environment variables dynamically loaded from .env
# -----------------------------------------------------------------------------
bq_env_keys = [
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GCP_RESOURCES_LOCATION",
    "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY",
    "OTEL_SEMCONV_STABILITY_OPT_IN",
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT",
    "DATASET_ID",
]
env_vars = {key: os.environ[key] for key in bq_env_keys if key in os.environ}

# -----------------------------------------------------------------------------
# Explicitly append Production Runtime URIs to the env_vars payload dictionary
# -----------------------------------------------------------------------------
env_vars["GOOGLE_CLOUD_LOCATION"] = "global"

# Get staging & artifact GCS bucket from environment (loaded from .env)
staging_bucket_uri = os.environ.get("ADK_ARTIFACT_SERVICE_URI")
if not staging_bucket_uri:
    raise ValueError("ADK_ARTIFACT_SERVICE_URI is not set. Please set it in your .env file.")

env_vars["ADK_SESSION_SERVICE_URI"] = "agentengine://"
env_vars["ADK_MEMORY_SERVICE_URI"] = "agentengine://"
env_vars["ADK_ARTIFACT_SERVICE_URI"] = staging_bucket_uri

requirements_list = [
    "google-genai",
    "google-auth>=2.53.0",
    "google-adk[agent-identity,a2a]>=2.1.0",
    "a2a-sdk>=0.3.4,<0.4",
    "google-cloud-aiplatform[agent_engines]>=1.154.0",
    "python-dotenv",
    "pydantic",
    "cloudpickle",
    "pyyaml",
    "google-api-core",
    "google-cloud-bigquery",
    "google-cloud-geminidataanalytics",
    "google-cloud-storage",
]

service_account = f"google-cloud-ops-agent-sa@{PROJECT_ID}.iam.gserviceaccount.com"

print(f"Deploying 'log_analytics_agent' to AgentPlatform in a single step...")

deploy_config = {
    "display_name": "Cloud Log Analytics Agent",
    "description": "Generic Cloud Log Analytics Agent utilizing the Conversational Analytics API and dynamic log context.",
    "requirements": requirements_list,
    "extra_packages": ["log_analytics_agent"],
    "env_vars": env_vars,
    "service_account": service_account,
    # "identity_type": vertexai_types.IdentityType.SERVICE_ACCOUNT,
    "staging_bucket": staging_bucket_uri,
    "python_version": "3.13",
}

# Create a new resource with your agent deployed to Agent Runtime.
remote_agent = client.agent_engines.create(
    agent=adk_app,
    config=deploy_config
)

print(f"\nSUCCESS: Agent deployed successfully to Agent Runtime!")
print(f"AgentPlatform Resource Name: {remote_agent.api_resource.name}")
print(f"To run chat sessions on this deployed agent, use the resource URI: {remote_agent.api_resource.name}")
