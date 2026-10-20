# Azure Container Apps + Streamlit + Foundry Agent

This sample creates a simple Streamlit app that talks to an Azure AI Foundry agent. It is designed to be deployed to Azure Container Apps.

## Prerequisites

- Azure subscription
- Azure AI Foundry project
- Azure AI model deployment (for example `gpt-4o-mini`)
- Azure CLI installed and logged in
- Docker installed if you want to build locally

## Local setup

1. Create a virtual environment and install dependencies:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copy the example environment file and fill in your values:

   ```bash
   copy .env.example .env
   ```

3. Run the app locally:

   ```bash
   streamlit run app.py
   ```

## Azure Container Apps deployment

1. Build the container image and push it to Azure Container Registry (ACR):

   ```bash
   az acr build --registry <acr-name> --image foundry-streamlit-app:latest .
   ```

2. Create a Container App using the built image.

3. Set the following environment variables in the Container App:

   - `PROJECT_ENDPOINT` (preferred) or `PROJECT_CONNECTION_STRING`
   - `MODEL_DEPLOYMENT_NAME`
   - `AGENT_NAME`
   - `FOUNDRY_AGENT_ID` (recommended)

   Set `FOUNDRY_AGENT_ID` to an existing agent so container restarts and scale-out events
   reuse that agent instead of creating a new one each time. If it is not set, the app
   reuses the first agent matching `AGENT_NAME`, and only creates an agent if none exists.

   List your agents to find the ID:

   ```python
   for a in project_client.agents.list_agents():
       print(a.id, a.name, a.model)
   ```

4. Grant the Container App managed identity access to the Azure AI Foundry project.

   Example role assignments include Azure AI Developer or the relevant project permissions for the model and agent endpoint.

5. In the Azure Portal, configure the container port as `8501`.

## Notes

- `DefaultAzureCredential` is used for authentication.
- In Azure Container Apps, attach a managed identity and grant it access to your Azure AI Foundry project.
- This sample is intentionally simple and can be used as a starting point for a production-grade agent chat app.
