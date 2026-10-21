import os

import streamlit as st
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from openai import OpenAI

# Loads .env for local runs; in Azure Container Apps the values come from app settings.
load_dotenv()

FOUNDRY_SCOPE = "https://ai.azure.com/.default"
DEFAULT_AGENT_INSTRUCTIONS = "You are a helpful assistant. Keep replies concise but informative. Answer clearly and use markdown when useful. Short responses are preferred."


def get_project_endpoint():
    project_endpoint = os.getenv("PROJECT_ENDPOINT")
    if project_endpoint:
        return project_endpoint.rstrip("/")

    conn_str = os.getenv("PROJECT_CONNECTION_STRING")
    if not conn_str:
        raise ValueError(
            "PROJECT_ENDPOINT environment variable is not set. "
            "If you use a connection string, set PROJECT_CONNECTION_STRING to the Azure AI Foundry project connection string."
        )

    values = {}
    for part in conn_str.split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            values[key.strip().lower()] = value.strip()

    endpoint = values.get("endpoint")
    project_name = values.get("project_name")
    if not endpoint:
        raise ValueError("PROJECT_CONNECTION_STRING must include an 'endpoint' value.")
    if not project_name:
        raise ValueError("PROJECT_CONNECTION_STRING must include a 'project_name' value.")

    combined = endpoint.rstrip("/")
    if "/api/projects/" not in combined:
        combined = f"{combined}/api/projects/{project_name}"
    return combined


def get_agent_name():
    agent_name = os.getenv("FOUNDRY_AGENT_ID") or os.getenv("AGENT_NAME")
    if not agent_name:
        raise ValueError(
            "FOUNDRY_AGENT_ID environment variable is not set. "
            "Set it to the name of the Foundry agent, for example 'streamlit-agent-new-version'."
        )
    return agent_name


def ensure_agent_exists(endpoint, credential, agent_name):
    """Create the agent if the project has none with this name; otherwise leave it untouched."""
    with AIProjectClient(endpoint=endpoint, credential=credential) as project:
        try:
            project.agents.get(agent_name=agent_name)
            return
        except ResourceNotFoundError:
            pass

        model = os.getenv("FOUNDRY_MODEL_NAME")
        if not model:
            raise ValueError(
                f"Agent '{agent_name}' does not exist and FOUNDRY_MODEL_NAME is not set. "
                "Set it to a model deployment name so the agent can be created."
            )
        project.agents.create_version(
            agent_name=agent_name,
            definition=PromptAgentDefinition(
                model=model,
                instructions=os.getenv("AGENT_INSTRUCTIONS") or DEFAULT_AGENT_INSTRUCTIONS,
            ),
        )


@st.cache_resource
def get_agent_session():
    endpoint = get_project_endpoint()
    agent_name = get_agent_name()
    credential = DefaultAzureCredential()
    ensure_agent_exists(endpoint, credential, agent_name)

    # The Foundry agent speaks the OpenAI-compatible Responses protocol, served under /openai/v1.
    token_provider = get_bearer_token_provider(credential, FOUNDRY_SCOPE)
    client = OpenAI(base_url=f"{endpoint}/openai/v1", api_key=token_provider())
    return client, token_provider, agent_name


def get_agent_reply(client, token_provider, agent_name, message_text, previous_response_id=None):
    # The credential caches tokens, so this only performs a refresh near expiry.
    client.api_key = token_provider()

    request = {
        "input": message_text,
        "extra_body": {
            "agent_reference": {"type": "agent_reference", "name": agent_name}
        },
    }
    if previous_response_id:
        request["previous_response_id"] = previous_response_id

    response = client.responses.create(**request)

    if getattr(response, "status", None) == "failed":
        raise RuntimeError(f"Agent run failed: {getattr(response, 'error', 'unknown error')}")

    reply = (response.output_text or "").strip()
    if not reply:
        reply = "The agent did not return any text for that message."
    return response.id, reply


if st.runtime.exists():
    st.set_page_config(page_title="Foundry Agent Chat", page_icon="🤖", layout="wide")

    st.title("Azure Foundry Agent Chat")
    st.caption("A simple Streamlit app deployed to Azure Container Apps using a Foundry agent.")

    if "messages" not in st.session_state:
        st.session_state.messages = []
        st.session_state.previous_response_id = None

    try:
        client, token_provider, agent_name = get_agent_session()
    except Exception as exc:
        st.error(
            "The app could not initialize the Azure Foundry agent. Check your environment variables and Azure login. "
            f"Details: {exc}"
        )
        st.stop()

    with st.sidebar:
        st.header("Settings")
        st.write(f"Agent: {agent_name}")
        st.write(f"Last response: {st.session_state.previous_response_id or '-'}")
        if st.button("Clear chat"):
            st.session_state.messages = []
            st.session_state.previous_response_id = None
            st.rerun()

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ask the agent anything..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    response_id, reply = get_agent_reply(
                        client,
                        token_provider,
                        agent_name,
                        prompt,
                        st.session_state.previous_response_id,
                    )
                    st.session_state.previous_response_id = response_id
                    st.markdown(reply)
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                except Exception as exc:
                    error_message = f"Error: {exc}"
                    st.error(error_message)
                    st.session_state.messages.append({"role": "assistant", "content": error_message})
