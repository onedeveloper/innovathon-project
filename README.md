# Innovathon Project: MCP Date/Time and SQLite Agent Application

This project implements a local application demonstrating the Model Context Protocol (MCP) with specialized agents (MCP Servers) providing Date/Time and SQLite functionalities to a Large Language Model (LLM) served by Ollama.

The system consists of:
*   **Ollama:** Runs the LLM locally.
*   **MCP Date/Time Server:** Provides tools for date/time operations.
*   **MCP SQLite Server:** Provides tools and resources for interacting with a local SQLite database.
*   **MCP Gateway:** Orchestrates communication between the client, servers, and Ollama.
*   **MCP Client:** A simple command-line interface for interacting with the system.

See `ARCHITECTURE.md` for a detailed architectural overview and `PLAN.md` for the implementation plan.

## Prerequisites

*   **Python:** Version 3.11 or higher recommended (as specified in `pyproject.toml`).
*   **uv:** The Python package installer and virtual environment manager used in this project. Install from [https://astral.sh/uv](https://astral.sh/uv).
*   **Ollama:** The local LLM serving platform. Download and install from [https://ollama.ai/](https://ollama.ai/).
*   **Git:** For cloning the repository.
*   **(Recommended) `gh` CLI:** For interacting with GitHub (used during initial setup).

## Setup Instructions

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/onedeveloper/innovathon-project.git
    cd innovathon-project
    ```

2.  **Install `uv`:** If you haven't already, install `uv` following the instructions on their website.

3.  **Create Virtual Environment:**
    ```bash
    uv venv
    ```
    This creates a `.venv` directory. You don't typically need to activate it manually, as `uv run` handles it.

4.  **Install Dependencies:**
    ```bash
    uv sync
    ```
    This command installs all dependencies listed in `pyproject.toml` and `uv.lock` into the `.venv`.

5.  **Configure Environment:**
    *   Copy the example environment file:
        ```bash
        cp .env.example .env
        ```
    *   Review the `.env` file and adjust settings if necessary (e.g., `OLLAMA_API_BASE_URL`, ports if defaults conflict). Ensure the `LOG_LEVEL` is set appropriately (e.g., `INFO` or `DEBUG`).

6.  **Setup Ollama:**
    *   Ensure the Ollama application/service is running.
    *   Pull the required LLM model (the gateway currently uses `gemma3:27b`):
        ```bash
        ollama pull gemma3:27b
        ```
    *   Verify Ollama is accessible at the `OLLAMA_API_BASE_URL` specified in `.env`.

## Running the Application

You need to run the Ollama service and the four Python components (Date/Time Server, SQLite Server, Gateway, Client) simultaneously.

1.  **Ensure Ollama is running.**

2.  **Open four separate terminal windows/tabs.**

3.  **Navigate to the project root directory (`innovathon-project`) in each terminal.**

4.  **Run each component using `python`:**

    *(Note: We use direct `python` commands here instead of `uv run <script_alias>` because `uv sync` in version 0.6.12 has a parsing issue with the `[tool.uv.scripts]` section in `pyproject.toml`. Running `python` directly still uses the correct interpreter from the `.venv` environment if you activated it, or you can use `uv run python <path_to_script>` which also works.)*

    *   Terminal 1: **Date/Time Server**
        ```bash
        python server_datetime/main.py
        # Or: uv run python server_datetime/main.py
        ```
    *   Terminal 2: **SQLite Server**
        ```bash
        python server_sqlite/main.py
        # Or: uv run python server_sqlite/main.py
        ```
        *(Note: This will create the `data/mydatabase.db` file if it doesn't exist)*
    *   Terminal 3: **Gateway**
        ```bash
        python gateway/main.py
        # Or: uv run python gateway/main.py
        ```
    *   Terminal 4: **Client**
        ```bash
        python client/cli.py
        # Or: uv run python client/cli.py
        ```

5.  **Interact:** The client will start in Terminal 4. Type your prompts and press Enter. Observe the logs in all terminals to see the interactions. Type `quit` or `exit` in the client terminal to stop it.

**Note:** The current implementation uses **placeholders** for the actual MCP communication between the Gateway and the Servers, and between the Client and the Gateway. The core logic flow is present, but network calls via MCP are simulated.

## Development

*   **Dependencies:** Add new dependencies using `uv add <package_name>`.
*   **Shared Code:** Common utilities are placed in the `common/` directory, which is installed as an editable package (`mcp_common_utils`). Changes in `common/` should be reflected when components are restarted.
*   **Scripts:** The `[tool.uv.scripts]` section in `pyproject.toml` is currently commented out due to a parsing issue with `uv sync` in `uv` version 0.6.12. Use direct `python <path_to_script>` commands or `uv run python <path_to_script>` instead of aliases.