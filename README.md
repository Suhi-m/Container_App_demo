# Azure Container Apps + Streamlit + Foundry Agent

A simple Streamlit chat app that talks to an Azure AI Foundry agent, designed to run in Azure Container Apps.

The app calls the agent through the **Responses API**, which is the protocol used by agents
created in the current Foundry portal. The agent is referenced by name, and conversation
history is carried with `previous_response_id`.

## Prerequisites

- Azure subscription
- Azure AI Foundry project
- A model deployed in the Foundry project (only used if the app has to create the agent)
- Azure CLI installed and logged in

## Local setup

1. Install dependencies into the project virtual environment:

   ```bash
   uv pip install --python .venv\Scripts\python.exe -r requirements.txt
   ```

   The bundled `.venv` is uv-managed and has no `pip`. If you prefer a standard venv:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copy the example environment file and fill in your values:

   ```bash
   copy .env.example .env
   ```

3. Run the app:

   ```bash
   streamlit run app.py
   ```

## Configuration

| Variable | Required | Description |
| --- | --- | --- |
| `PROJECT_ENDPOINT` | Yes | Foundry project endpoint, ending in `/api/projects/<project-name>` |
| `FOUNDRY_AGENT_ID` | Yes | Name of the agent. For portal-created agents the name is also the ID |
| `FOUNDRY_MODEL_NAME` | Only if the agent does not exist | Model deployment name used to create the agent |
| `AGENT_INSTRUCTIONS` | No | Instructions for an agent the app creates. Defaults to a general assistant prompt |
| `AGENT_NAME` | No | Fallback used only when `FOUNDRY_AGENT_ID` is not set |
| `PROJECT_CONNECTION_STRING` | No | Alternative to `PROJECT_ENDPOINT` |

On startup the app looks up the agent by name. If it exists it is used unchanged; if it
does not, the app creates it from `FOUNDRY_MODEL_NAME` and `AGENT_INSTRUCTIONS`. An existing
agent is never modified. Creating an agent needs more than invoke access, so the identity
must be allowed to write agents in the project.

### Finding your agent name

```bash
az rest --method get \
  --url "<PROJECT_ENDPOINT>/agents?api-version=v1" \
  --resource "https://ai.azure.com"
```

The `id` field of each entry is the value to use for `FOUNDRY_AGENT_ID`.

## Azure Container Apps deployment

1. Build and push the image, or deploy from a Git repository:

   ```bash
   az acr build --registry <acr-name> --image foundry-streamlit-app:latest .
   ```

2. Create the Container App from that image.

3. Add the environment variables from the table above under
   **Application → Containers → Edit → Environment variables**.

4. Enable a system-assigned managed identity under **Identity**.

5. Grant that identity access to the Foundry resource under **Access control (IAM)**.
   Assign **Foundry Agent Consumer** for least privilege, or **Foundry User** if the
   former is unavailable. Do not use **Azure AI Developer**, which applies to
   Azure Machine Learning workspaces and Foundry hubs rather than Foundry projects.

6. Under **Ingress**, set the target port to match the port the app actually listens on
   (`8501` when started with the command below) and enable external ingress.

   ```bash
   streamlit run app.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true
   ```

## Notes

- Authentication uses `DefaultAzureCredential` with the `https://ai.azure.com/.default`
  scope. Locally this is your Azure CLI login; in Container Apps it is the managed identity.
- Conversation history lives in Streamlit session state, so it is lost if a user's session
  moves to another replica or the container restarts. Persist `previous_response_id`
  externally if durable history is needed.
- Any tools enabled on the agent, such as web search, work automatically. No app change is
  required to add or remove them.
