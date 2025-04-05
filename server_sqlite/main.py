import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any

import uvicorn
from dotenv import load_dotenv
from modelcontextprotocol import FastMCP, ToolInput, tool, prompt, resource
from pydantic import BaseModel, Field

# --- Project Setup ---
# Determine the root directory of the project
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Load environment variables from .env file in the project root
dotenv_path = os.path.join(PROJECT_ROOT, '.env')
load_dotenv(dotenv_path=dotenv_path)

# --- Logging Setup ---
try:
    from mcp_common_utils.logging_config import setup_logging
    setup_logging("sqlite-server")
except ImportError:
    print("Error: Could not import setup_logging. Make sure 'common' is installed editably.")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

logger = logging.getLogger("sqlite-server")

# --- Error Utility ---
try:
    from mcp_common_utils.errors import create_error_response
except ImportError:
    def create_error_response(error_type: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {"error": {"type": error_type, "message": message, "details": details or {}}}

# --- Configuration ---
HOST = os.getenv("SQLITE_SERVER_HOST", "0.0.0.0")
try:
    PORT = int(os.getenv("SQLITE_SERVER_PORT", "8002"))
except ValueError:
    logger.error("Invalid SQLITE_SERVER_PORT defined in .env. Using default 8002.")
    PORT = 8002
DB_PATH_STR = os.getenv("SQLITE_DB_PATH", "data/mydatabase.db")
DB_PATH = Path(PROJECT_ROOT) / DB_PATH_STR # Ensure DB path is relative to project root

# --- Database Initialization ---
def initialize_database():
    """Creates the database file and insights table if they don't exist."""
    try:
        # Ensure the directory exists
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Ensuring database directory exists: {DB_PATH.parent}")

        # Connect to the database (creates the file if it doesn't exist)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        logger.info(f"Connected to database: {DB_PATH}")

        # Check if insights table exists and create it if not
        cursor.execute("""
            SELECT name FROM sqlite_master WHERE type='table' AND name='insights';
        """)
        if cursor.fetchone() is None:
            logger.info("Creating 'insights' table.")
            cursor.execute("""
                CREATE TABLE insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    content TEXT NOT NULL
                );
            """)
            conn.commit()
            logger.info("'insights' table created successfully.")
        else:
            logger.info("'insights' table already exists.")

        conn.close()

    except sqlite3.Error as e:
        logger.error(f"Database initialization error: {e}", exc_info=True)
        # In a real app, might want to raise this or handle more gracefully
        raise RuntimeError(f"Failed to initialize database: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error during database initialization: {e}", exc_info=True)
        raise RuntimeError(f"Unexpected error initializing database: {e}") from e

# Initialize DB on startup
initialize_database()

# --- FastMCP Application ---
app = FastMCP(
    title="MCP SQLite Server",
    description="Provides tools and resources for interacting with a local SQLite database.",
)

# --- Helper Function for DB Connection ---
def get_db_connection():
    """Establishes and returns a database connection and cursor."""
    try:
        conn = sqlite3.connect(DB_PATH)
        # Return rows as dictionary-like objects
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        return conn, cursor
    except sqlite3.Error as e:
        logger.error(f"Failed to connect to database {DB_PATH}: {e}", exc_info=True)
        # Re-raise or handle appropriately; here we let it propagate up
        raise

# --- Tools Implementation ---

class QueryInput(BaseModel):
    query: str = Field(..., description="The SQL query to execute.")

class TableNameInput(BaseModel):
    table_name: str = Field(..., description="The name of the target table.")

class InsightInput(BaseModel):
    insight: str = Field(..., description="The text insight to append.")

@tool(
    name="read_query",
    description="Executes a read-only (SELECT) SQL query against the database and returns the results.",
    input_model=QueryInput,
)
def read_query(input_data: QueryInput) -> List[Dict[str, Any]] | Dict[str, Any]:
    """Executes a SELECT query and returns results."""
    logger.info(f"Executing read_query: {input_data.query}")
    # Basic check to prevent modification queries (can be improved)
    if not input_data.query.strip().upper().startswith("SELECT"):
        logger.warning(f"Attempted non-SELECT query in read_query: {input_data.query}")
        return create_error_response(
            error_type="SecurityError",
            message="Only SELECT queries are allowed with the read_query tool.",
            details={"query": input_data.query}
        )

    conn, cursor = None, None
    try:
        conn, cursor = get_db_connection()
        cursor.execute(input_data.query)
        results = cursor.fetchall()
        # Convert Row objects to dictionaries
        results_dict = [dict(row) for row in results]
        logger.info(f"read_query successful, returned {len(results_dict)} rows.")
        return results_dict
    except sqlite3.Error as e:
        logger.error(f"Error executing read_query '{input_data.query}': {e}", exc_info=True)
        return create_error_response(
            error_type="DatabaseError",
            message=f"Failed to execute read query: {e}",
            details={"query": input_data.query}
        )
    finally:
        if conn:
            conn.close()

@tool(
    name="write_query",
    description="Executes a write (INSERT, UPDATE, DELETE) SQL query against the database and returns the number of affected rows.",
    input_model=QueryInput,
)
def write_query(input_data: QueryInput) -> Dict[str, Any]:
    """Executes a write query and returns affected rows."""
    logger.info(f"Executing write_query: {input_data.query}")
    query_upper = input_data.query.strip().upper()
    # Basic check for allowed write operations
    if not (query_upper.startswith("INSERT") or query_upper.startswith("UPDATE") or query_upper.startswith("DELETE")):
        logger.warning(f"Attempted non-write query in write_query: {input_data.query}")
        return create_error_response(
            error_type="SecurityError",
            message="Only INSERT, UPDATE, or DELETE queries are allowed with the write_query tool.",
            details={"query": input_data.query}
        )

    conn, cursor = None, None
    try:
        conn, cursor = get_db_connection()
        cursor.execute(input_data.query)
        affected_rows = cursor.rowcount
        conn.commit()
        logger.info(f"write_query successful, affected rows: {affected_rows}.")
        return {"status": "success", "affected_rows": affected_rows}
    except sqlite3.Error as e:
        logger.error(f"Error executing write_query '{input_data.query}': {e}", exc_info=True)
        conn.rollback() # Rollback changes on error
        return create_error_response(
            error_type="DatabaseError",
            message=f"Failed to execute write query: {e}",
            details={"query": input_data.query}
        )
    finally:
        if conn:
            conn.close()

@tool(
    name="create_table",
    description="Executes a CREATE TABLE SQL query.",
    input_model=QueryInput,
)
def create_table(input_data: QueryInput) -> Dict[str, Any]:
    """Executes a CREATE TABLE query."""
    logger.info(f"Executing create_table: {input_data.query}")
    if not input_data.query.strip().upper().startswith("CREATE TABLE"):
        logger.warning(f"Attempted non-CREATE TABLE query in create_table: {input_data.query}")
        return create_error_response(
            error_type="SecurityError",
            message="Only CREATE TABLE queries are allowed with the create_table tool.",
            details={"query": input_data.query}
        )

    conn, cursor = None, None
    try:
        conn, cursor = get_db_connection()
        cursor.execute(input_data.query)
        conn.commit()
        logger.info(f"create_table successful for query: {input_data.query}")
        return {"status": "success", "message": "Table created successfully."}
    except sqlite3.Error as e:
        logger.error(f"Error executing create_table '{input_data.query}': {e}", exc_info=True)
        conn.rollback()
        return create_error_response(
            error_type="DatabaseError",
            message=f"Failed to create table: {e}",
            details={"query": input_data.query}
        )
    finally:
        if conn:
            conn.close()

@tool(
    name="list_tables",
    description="Lists all tables in the database.",
)
def list_tables() -> List[str] | Dict[str, Any]:
    """Lists all tables in the database."""
    logger.info("Executing list_tables tool.")
    conn, cursor = None, None
    try:
        conn, cursor = get_db_connection()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row['name'] for row in cursor.fetchall()]
        logger.info(f"list_tables successful, found tables: {tables}")
        return tables
    except sqlite3.Error as e:
        logger.error(f"Error executing list_tables: {e}", exc_info=True)
        return create_error_response(
            error_type="DatabaseError",
            message=f"Failed to list tables: {e}"
        )
    finally:
        if conn:
            conn.close()

@tool(
    name="describe_table",
    description="Describes the schema (columns and types) of a specific table.",
    input_model=TableNameInput,
)
def describe_table(input_data: TableNameInput) -> List[Dict[str, Any]] | Dict[str, Any]:
    """Describes the schema of a table."""
    table_name = input_data.table_name
    logger.info(f"Executing describe_table for table: {table_name}")
    conn, cursor = None, None
    try:
        conn, cursor = get_db_connection()
        # Use PRAGMA table_info, ensuring table name is safely handled (no direct injection)
        cursor.execute(f"PRAGMA table_info({sqlite3.complete_statement(f'"{table_name}"')});") # Basic quoting
        schema_info = cursor.fetchall()
        if not schema_info:
             logger.warning(f"Table '{table_name}' not found during describe_table.")
             return create_error_response(
                 error_type="NotFoundError",
                 message=f"Table '{table_name}' not found.",
                 details={"table_name": table_name}
             )
        schema_dict = [dict(row) for row in schema_info]
        logger.info(f"describe_table successful for table '{table_name}'.")
        return schema_dict
    except sqlite3.Error as e:
        logger.error(f"Error executing describe_table for '{table_name}': {e}", exc_info=True)
        return create_error_response(
            error_type="DatabaseError",
            message=f"Failed to describe table '{table_name}': {e}",
            details={"table_name": table_name}
        )
    finally:
        if conn:
            conn.close()

@tool(
    name="append_insight",
    description="Appends a new text insight to the 'insights' table.",
    input_model=InsightInput,
)
def append_insight(input_data: InsightInput) -> Dict[str, Any]:
    """Appends an insight to the insights table."""
    insight_text = input_data.insight
    logger.info(f"Executing append_insight with text: '{insight_text[:50]}...'")
    conn, cursor = None, None
    try:
        conn, cursor = get_db_connection()
        cursor.execute("INSERT INTO insights (content) VALUES (?)", (insight_text,))
        conn.commit()
        new_id = cursor.lastrowid
        logger.info(f"append_insight successful, new insight ID: {new_id}")
        return {"status": "success", "message": "Insight appended successfully.", "id": new_id}
    except sqlite3.Error as e:
        logger.error(f"Error executing append_insight: {e}", exc_info=True)
        conn.rollback()
        return create_error_response(
            error_type="DatabaseError",
            message=f"Failed to append insight: {e}",
            details={"insight_preview": insight_text[:50] + "..."}
        )
    finally:
        if conn:
            conn.close()

# --- Resource Implementation ---

@resource(uri="memo://insights")
def get_insights_resource() -> str | Dict[str, Any]:
    """Provides the content of the latest insights from the database."""
    logger.info("Accessing memo://insights resource.")
    conn, cursor = None, None
    try:
        conn, cursor = get_db_connection()
        # Get latest 10 insights, newest first
        cursor.execute("SELECT timestamp, content FROM insights ORDER BY timestamp DESC LIMIT 10")
        insights = cursor.fetchall()
        # Format as a simple string list
        formatted_insights = [f"- {row['timestamp']}: {row['content']}" for row in insights]
        logger.info(f"memo://insights resource returned {len(formatted_insights)} items.")
        return "\n".join(formatted_insights) if formatted_insights else "No insights recorded yet."
    except sqlite3.Error as e:
        logger.error(f"Error accessing memo://insights resource: {e}", exc_info=True)
        return create_error_response(
            error_type="DatabaseError",
            message=f"Failed to retrieve insights: {e}"
        )
    finally:
        if conn:
            conn.close()

# --- Prompt Implementation ---

class DemoPromptInput(BaseModel):
    topic: str = Field(..., description="The topic to generate a demo schema and data for.")

@prompt(
    name="mcp-demo",
    description="Generates a sample SQLite schema and data based on a topic, then guides the user to query it using the available tools.",
    input_model=DemoPromptInput,
)
def mcp_demo_prompt(input_data: DemoPromptInput) -> str:
    """Generates a guided demo prompt based on a topic."""
    topic = input_data.topic
    logger.info(f"Generating mcp-demo prompt for topic: {topic}")

    # Example: Generate a simple schema and insert some data based on the topic
    # In a real scenario, this might involve more complex logic or even calling an LLM
    table_name = topic.lower().replace(" ", "_") + "_examples"
    schema_sql = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        value REAL
    );
    """
    insert_sql = f"INSERT INTO {table_name} (name, value) VALUES (?, ?);"
    sample_data = [
        (f"{topic} Sample A", 10.5),
        (f"{topic} Sample B", 22.0),
        (f"{topic} Sample C", 7.8),
    ]

    conn, cursor = None, None
    try:
        conn, cursor = get_db_connection()
        logger.info(f"Executing schema for demo: {schema_sql.strip()}")
        cursor.execute(schema_sql)
        logger.info(f"Executing inserts for demo into table {table_name}")
        cursor.executemany(insert_sql, sample_data)
        conn.commit()
        logger.info("Demo data created successfully.")
    except sqlite3.Error as e:
        logger.error(f"Error setting up demo data for topic '{topic}': {e}", exc_info=True)
        conn.rollback()
        return f"Sorry, I encountered an error while setting up the demo for '{topic}': {e}. Please try again."
    finally:
        if conn:
            conn.close()

    # Construct the guided prompt for the user/LLM
    guidance = f"""
Okay, I've set up a demonstration for the topic '{topic}'.
A table named '{table_name}' has been created with the following columns: id (INTEGER), name (TEXT), value (REAL).
I've also added some sample data.

You can now use the available SQLite tools to explore this data. Try asking things like:
- "List all tables" (using the `list_tables` tool)
- "Describe the table {table_name}" (using the `describe_table` tool)
- "Show me all data from the {table_name} table" (using the `read_query` tool with 'SELECT * FROM {table_name};')
- "What is the average value in the {table_name} table?" (using `read_query` with 'SELECT AVG(value) FROM {table_name};')

What would you like to query first?
"""
    return guidance.strip()

# Register all components
app.include_tool(read_query)
app.include_tool(write_query)
app.include_tool(create_table)
app.include_tool(list_tables)
app.include_tool(describe_table)
app.include_tool(append_insight)
app.include_resource(get_insights_resource)
app.include_prompt(mcp_demo_prompt)

# --- Server Runner ---
if __name__ == "__main__":
    logger.info(f"Starting SQLite MCP Server on {HOST}:{PORT}")
    logger.info(f"Using database at: {DB_PATH}")
    uvicorn.run(app, host=HOST, port=PORT)