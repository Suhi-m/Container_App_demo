import os

import streamlit as st
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Loads .env for local runs; in Azure Container Apps the values come from app settings.
load_dotenv()


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


def get_project_client():
    endpoint = get_project_endpoint()
    return AIProjectClient(
        endpoint=endpoint,
        credential=DefaultAzureCredential(),
    )


def get_assistant_reply(project_client, thread_id, agent_id, message_text):
    project_client.agents.messages.create(
        thread_id=thread_id,
        role="user",
        content=message_text,
    )

    run = project_client.agents.runs.create_and_process(
        thread_id=thread_id,
        agent_id=agent_id,
    )

    if getattr(run, "status", None) == "failed":
        raise RuntimeError(f"Agent run failed: {getattr(run, 'last_error', 'unknown error')}")

    messages = list(project_client.agents.messages.list(thread_id=thread_id, order="desc", limit=20))

    for message in messages:
        if getattr(message, "role", None) == "assistant":
            for item in getattr(message, "content", []):
                text_value = getattr(getattr(item, "text", None), "value", None)
                if text_value:
                    return text_value

    return "The agent did not return any text for that message."


AGENT_INSTRUCTIONS = (
    "You are a helpful assistant. Keep replies concise but informative. "
    "Answer clearly and use markdown when useful."
)


@st.cache_resource
def get_or_create_agent():
    project_client = get_project_client()
    agent_name = os.getenv("AGENT_NAME", "azure-container-app-agent")

    # Reuse an explicitly configured agent so restarts and scale-out don't create duplicates.
    agent_id = os.getenv("FOUNDRY_AGENT_ID")
    if agent_id:
        return project_client, project_client.agents.get_agent(agent_id)

    # Fall back to reusing an agent already created under the same name.
    for existing in project_client.agents.list_agents():
        if getattr(existing, "name", None) == agent_name:
            return project_client, existing

    model_deployment = os.getenv("MODEL_DEPLOYMENT_NAME")
    if not model_deployment:
        raise ValueError("MODEL_DEPLOYMENT_NAME environment variable is not set.")

    agent = project_client.agents.create_agent(
        model=model_deployment,
        name=agent_name,
        instructions=AGENT_INSTRUCTIONS,
    )
    return project_client, agent


if st.runtime.exists():
    st.set_page_config(page_title="Foundry Agent Chat", page_icon="🤖", layout="wide")

    st.title("Azure Foundry Agent Chat")
    st.caption("A simple Streamlit app deployed to Azure Container Apps using a Foundry agent.")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "thread_id" not in st.session_state:
        try:
            project_client, agent = get_or_create_agent()
            thread = project_client.agents.threads.create()
            st.session_state.project_client = project_client
            st.session_state.agent = agent
            st.session_state.thread_id = thread.id
        except Exception as exc:
            st.error(
                "The app could not initialize the Azure Foundry agent. Check your environment variables and Azure login. "
                f"Details: {exc}"
            )
            st.stop()

    with st.sidebar:
        st.header("Settings")
        st.write(f"Agent: {st.session_state.agent.name}")
        st.write(f"Thread: {st.session_state.thread_id}")
        if st.button("Clear chat"):
            st.session_state.messages = []
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
                    reply = get_assistant_reply(
                        st.session_state.project_client,
                        st.session_state.thread_id,
                        st.session_state.agent.id,
                        prompt,
                    )
                    st.markdown(reply)
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                except Exception as exc:
                    error_message = f"Error: {exc}"
                    st.error(error_message)
                    st.session_state.messages.append({"role": "assistant", "content": error_message})
