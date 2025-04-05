# REFINED PLAN.md - MCP Date/Time and SQLite Agent Application

This document outlines the steps to implement the local MCP-based application featuring Date/Time and SQLite agents using Ollama, incorporating decisions on configuration, logging, dependencies, caching, error handling, and persistence.

**Target Environment:** Macbook Pro M4 Max (128GB RAM), macOS

**Core Technologies:**
* Python 3.x
* Model Context Protocol (MCP)
* `FastMCP` Python SDK (`modelcontextprotocol/python-sdk`)
* `FastAgent` (Optional, for Client) (`evalstate/fast-agent`)
* Ollama
* SQLite3
* `uv` (Astral) for environment and package management
* `python-dotenv` for configuration loading

---

## Phase 1: Setup and Prerequisites

1.  **Install `uv`:**
    *   Follow instructions at [https://astral.sh/uv](https://astral.sh/uv) (e.g., `curl -LsSf https://astral.sh/uv/install.sh | sh` or `pip install uv`).
2.  **Initialize Project & Environment:**
    *   Create a root directory for the project.
    *   Navigate into the directory.
    *   Initialize `uv` project (creates `pyproject.toml` if needed): `uv init` (review and adjust `pyproject.toml` if necessary).
    *   Create the virtual environment: `uv venv` (creates `.venv`).
    *   *(Optional but recommended for interactive use)* Activate it: `source .venv/bin/activate`
3.  **Create Configuration File:**
    *   Create a `.env` file in the project root.
    *   Add initial configuration variables (adjust values as needed):
        ```dotenv
        # Logging Level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        LOG_LEVEL=INFO

        # Ollama Configuration
        OLLAMA_API_BASE_URL=http://localhost:11434

        # Gateway Configuration
        GATEWAY_HOST=0.0.0.0
        GATEWAY_PORT=8000
        GATEWAY_CACHE_REFRESH_MINUTES=30

        # Date/Time Server Configuration
        DATETIME_SERVER_HOST=0.0.0.0
        DATETIME_SERVER_PORT=8001

        # SQLite Server Configuration
        SQLITE_SERVER_HOST=0.0.0.0
        SQLITE_SERVER_PORT=8002
        SQLITE_DB_PATH=data/mydatabase.db
        ```
    *   Create a `.env.example` file mirroring `.env` but with placeholder values, and add `.env` to `.gitignore`.
4.  **Install Dependencies:**
    *   Use `uv` to add required packages, which updates `pyproject.toml`:
        ```bash
        uv add modelcontextprotocol
        uv add uvicorn
        uv add httpx
        uv add python-dotenv
        # Optional, if using FastAgent for the client:
        # uv add fast-agent
        ```
5.  **Install Ollama:**
    *   Download and install Ollama for macOS from [ollama.ai](https://ollama.ai/).
    *   Pull a suitable LLM: `ollama pull llama3` (or another model).
    *   Verify Ollama is running and accessible at the `OLLAMA_API_BASE_URL` defined in `.env`.
6.  **Project Structure:** Create subdirectories (e.g., `client`, `gateway`, `server_datetime`, `server_sqlite`, `common`, `data`). Create a `common` directory for shared utilities like logging setup and error structures.

## Phase 2: Implement MCP Server 1 (Date/Time Agent)

1.  **Create Server File:** `server_datetime/main.py`
2.  **Implement Logging Setup:** In `common/logging_config.py`, create a function to configure standard Python `logging` based on `LOG_LEVEL` from `.env`, outputting to console with timestamp, component name, and level. Call this setup function early in `server_datetime/main.py`.
3.  **Implement Configuration Loading:** Use `dotenv.load_dotenv()` and `os.getenv()` to load `DATETIME_SERVER_HOST` and `DATETIME_SERVER_PORT` in `server_datetime/main.py`.
4.  **Import Libraries:** `FastMCP`, `datetime`, `logging`, `os`.
5.  **Define Tools:**
    *   Implement `get_current_time()`: Returns current time string.
    *   Implement `get_current_date()`: Returns current date string.
    *   Implement `calculate_date_difference(start_date: str, end_date: str, unit: str)`: Parses dates, calculates difference.
6.  **Implement Error Handling:** Wrap tool logic in `try...except` blocks. Catch specific exceptions (e.g., `ValueError` for date parsing). Define a structured error format (e.g., in `common/errors.py`) and return detailed errors via FastMCP on failure. Log errors using the configured logger.
7.  **Create FastMCP Application:** `app = FastMCP()`
8.  **Register Tools:** Use `@app.tool(...)` decorators, providing clear descriptions.
9.  **Add Server Runner:** Use `uvicorn` to run the app, using loaded host/port configuration (e.g., `if __name__ == "__main__": ... uvicorn.run(app, host=HOST, port=PORT)`).
10. **Update `pyproject.toml` (Optional):** Add a script entry under `[tool.uv.scripts]` like `start-datetime = "python server_datetime/main.py"`.

## Phase 3: Implement MCP Server 2 (SQLite Agent)

1.  **Create Server File:** `server_sqlite/main.py`
2.  **Implement Logging & Configuration:** Similar to Phase 2, setup logging and load configuration (`SQLITE_SERVER_HOST`, `SQLITE_SERVER_PORT`, `SQLITE_DB_PATH`) from `.env`.
3.  **Import Libraries:** `FastMCP`, `sqlite3`, `logging`, `os`, `pathlib`.
4.  **Implement Database Initialization:**
    *   On startup, check if the database file at `SQLITE_DB_PATH` exists. If not, create the directory (`pathlib.Path(SQLITE_DB_PATH).parent.mkdir(parents=True, exist_ok=True)`) and the file.
    *   Establish a DB connection.
    *   Check if the required table for insights (e.g., `insights`) exists. If not, execute `CREATE TABLE insights (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, content TEXT);`. Log these actions.
5.  **Implement Tools (as per spec):**
    *   `read_query(query: str)`
    *   `write_query(query: str)`
    *   `create_table(query: str)`
    *   `list_tables()`
    *   `describe_table(table_name: str)`
    *   `append_insight(insight: str)`: Insert the insight into the `insights` table.
6.  **Implement Resource (`memo://insights`):**
    *   Define the `memo://insights` resource using `@app.resource`.
    *   The resource getter function should query the `insights` table (e.g., get the latest 10) and return the content.
    *   The `append_insight` tool implicitly updates the data backing this resource. Consider if FastMCP needs explicit notification for resource updates if clients subscribe.
7.  **Implement Prompt (`mcp-demo`):**
    *   Define the `mcp-demo` prompt using `@app.prompt`. Implement its logic.
8.  **Implement Error Handling:** Wrap tool/DB logic in `try...except sqlite3.Error` etc. Return detailed structured errors (from `common/errors.py`) and log them.
9.  **Create FastMCP Application & Register:** `app = FastMCP()`. Register tools, resource, prompt using decorators.
10. **Add Server Runner:** Use `uvicorn` with loaded host/port.
11. **Update `pyproject.toml` (Optional):** Add script `start-sqlite = "python server_sqlite/main.py"`.

## Phase 4: Implement MCP Model Gateway

1.  **Create Gateway File:** `gateway/main.py`
2.  **Implement Logging & Configuration:** Setup logging, load config (`GATEWAY_HOST`, `GATEWAY_PORT`, `OLLAMA_API_BASE_URL`, `DATETIME_SERVER_PORT`, `SQLITE_SERVER_PORT`, `GATEWAY_CACHE_REFRESH_MINUTES`) from `.env`. Determine server URLs (e.g., `http://localhost:{PORT}`).
3.  **Import Libraries:** `FastMCP`, `httpx`, `logging`, `os`, `asyncio`, `datetime`.
4.  **Implement Tool Definition Cache:**
    *   Create an in-memory cache (e.g., a dictionary) to store tool definitions fetched from servers.
    *   Implement a function to fetch definitions from a given server URL using `FastMCP` client capabilities.
    *   Implement a background task (`asyncio.create_task`) that runs periodically (based on `GATEWAY_CACHE_REFRESH_MINUTES`) to call the fetch function for both servers and update the cache. Handle potential connection errors during refresh.
    *   The main request handler should read from the cache. Fetch definitions on startup initially.
5.  **Create FastMCP Application:** `app = FastMCP()`
6.  **Implement Core Logic:**
    *   Define the main endpoint receiving client requests.
    *   On request:
        *   Read tool definitions from the cache.
        *   Format user prompt + cached tool definitions for Ollama API.
        *   Use `httpx.AsyncClient` to call Ollama API (`OLLAMA_API_BASE_URL`). Handle potential `httpx` errors.
        *   Parse Ollama response.
        *   **If tool call requested:** Extract details. Determine target server URL from cached definitions. Use `FastMCP` client to call the tool on the correct server. Handle potential errors returned by the server. (Optional: Send tool result back to Ollama for final phrasing).
        *   **If error occurred (Ollama/Server/Internal):** Log detailed error. Create structured error response (from `common/errors.py`).
        *   Return final response or structured error to the Client.
7.  **Implement Error Handling:** Catch errors during Ollama/Server communication, parsing, etc. Log details and return structured errors transparently.
8.  **Add Server Runner:** Use `uvicorn` with loaded host/port.
9.  **Update `pyproject.toml` (Optional):** Add script `start-gateway = "python gateway/main.py"`.

## Phase 5: Implement MCP Model Client

1.  **Create Client File:** `client/cli.py` (or similar)
2.  **Implement Logging & Configuration:** Setup logging, load Gateway URL (`http://{GATEWAY_HOST}:{GATEWAY_PORT}`) from `.env`.
3.  **Import Libraries:** `FastAgent` or `FastMCP`, `logging`, `os`, `argparse` (optional).
4.  **Implement Client Logic:**
    *   Use `FastAgent` or `FastMCP` client to connect to the Gateway URL.
    *   Create a loop for user input.
    *   Send prompt to Gateway.
    *   Receive response.
    *   **If response is an error:** Display the detailed technical error structure received.
    *   **If response is successful:** Display the content.
    *   Log interactions/errors. Handle connection errors to the Gateway.
    *   Add exit condition.
5.  **Update `pyproject.toml` (Optional):** Add script `start-client = "python client/cli.py"`.

## Phase 6: Integration, Testing, and Refinement

1.  **Run All Components:**
    *   Start Ollama service.
    *   In separate terminals (or using a process manager):
        *   `uv run start-datetime` (or `uv run python server_datetime/main.py`)
        *   `uv run start-sqlite` (or `uv run python server_sqlite/main.py`)
        *   `uv run start-gateway` (or `uv run python gateway/main.py`)
        *   `uv run start-client` (or `uv run python client/cli.py`)
2.  **Test Scenarios:**
    *   Simple LLM queries.
    *   Date/Time tool usage.
    *   SQLite tool usage (list, create, write, read, describe).
    *   `memo://insights` resource interaction (`append_insight`, check resource).
    *   `mcp-demo` prompt usage.
    *   **Error conditions:** Invalid dates, invalid SQL, non-existent tables, stopping a server while Gateway is running (test cache refresh and error handling).
3.  **Debug and Refine:** Use console logs (adjust `LOG_LEVEL` in `.env` to `DEBUG` if needed). Refine tool descriptions/prompts if LLM struggles. Ensure errors are propagated and displayed correctly.

## Phase 7: Documentation

1.  **README.md:** Create/update root `README.md` explaining the project, refined architecture, setup using `uv`, configuration via `.env`, and how to run components using `uv run`.
2.  **Code Comments:** Add comments to clarify complex logic, especially error handling, caching, and DB interactions.
3.  **`.env.example`:** Ensure this file is present and up-to-date.

---

## Architecture Summary (Mermaid)

```mermaid
graph TD
    subgraph "Refined Plan"
        A[Phase 1: Setup] --> B(Install uv);
        B --> C(uv init / pyproject.toml);
        C --> D(Create .env file);
        D --> E(uv add dependencies);
        E --> F(Define project structure);

        G[Phase 2: Date/Time Server] --> H(Implement tools);
        H --> I(Setup logging from .env);
        I --> J(Read config from .env);
        J --> K(Register tools w/ FastMCP);
        K --> L(Add uv run script);
        L --> L1(Implement structured error returns);


        M[Phase 3: SQLite Server] --> N(Implement tools);
        N --> O(Setup logging from .env);
        O --> P(Read config from .env);
        P --> Q(Implement DB auto-init logic);
        Q --> R(Implement insights resource w/ DB table persistence);
        R --> S(Implement prompt);
        S --> T(Register components w/ FastMCP);
        T --> U(Add uv run script);
        U --> V(Implement structured error returns);


        W[Phase 4: Gateway] --> X(Setup logging from .env);
        X --> Y(Read config from .env);
        Y --> Z(Implement periodic tool definition caching);
        Z --> AA(Implement Ollama interaction);
        AA --> BB(Implement tool routing);
        BB --> CC(Implement transparent error forwarding);
        CC --> DD(Add uv run script);

        EE[Phase 5: Client] --> FF(Setup logging from .env);
        FF --> GG(Read config from .env);
        GG --> HH(Implement connection to Gateway);
        HH --> II(Implement prompt loop);
        II --> JJ(Display responses / detailed errors);
        JJ --> KK(Add uv run script);

        LL[Phase 6: Integration/Testing] --> MM(Run all components via uv run);
        MM --> NN(Test scenarios, including error cases);
        NN --> OO(Debug using logs);

        PP[Phase 7: Documentation] --> QQ(Update README);
        QQ --> RR(Add code comments);
        RR --> SS(Ensure .env.example exists);
    end
