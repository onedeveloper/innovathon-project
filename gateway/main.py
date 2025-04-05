import json # Added for tool result formatting
import logging
import os
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import httpx
import uvicorn
from dotenv import load_dotenv
from modelcontextprotocol import FastMCP # Assuming MCPClient and ToolDefinition are part of the SDK or handled differently
from pydantic import BaseModel

# --- Project Setup ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(PROJECT_ROOT, '.env')
load_dotenv(dotenv_path=dotenv_path)

# --- Logging Setup ---
try:
    from mcp_common_utils.logging_config import setup_logging
    setup_logging("gateway")
except ImportError:
    print("Error: Could not import setup_logging. Make sure 'common' is installed editably.")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

logger = logging.getLogger("gateway")

# --- Error Utility ---
try:
    from mcp_common_utils.errors import create_error_response
except ImportError:
    def create_error_response(error_type: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {"error": {"type": error_type, "message": message, "details": details or {}}}

# --- Configuration ---
HOST = os.getenv("GATEWAY_HOST", "0.0.0.0")
try:
    PORT = int(os.getenv("GATEWAY_PORT", "8000"))
except ValueError:
    logger.error("Invalid GATEWAY_PORT defined in .env. Using default 8000.")
    PORT = 8000

OLLAMA_API_BASE_URL = os.getenv("OLLAMA_API_BASE_URL", "http://localhost:11434")
# Construct server URLs (assuming they run on localhost as per initial plan)
try:
    DATETIME_SERVER_PORT = int(os.getenv("DATETIME_SERVER_PORT", "8001"))
    SQLITE_SERVER_PORT = int(os.getenv("SQLITE_SERVER_PORT", "8002"))
    DATETIME_SERVER_URL = f"http://localhost:{DATETIME_SERVER_PORT}" # Adjust if host can differ
    SQLITE_SERVER_URL = f"http://localhost:{SQLITE_SERVER_PORT}"     # Adjust if host can differ
except ValueError:
     logger.error("Invalid server port defined in .env. Cannot construct server URLs.")
     # Exit or raise critical error? For now, log and proceed with potentially wrong defaults
     DATETIME_SERVER_URL = "http://localhost:8001"
     SQLITE_SERVER_URL = "http://localhost:8002"


try:
    CACHE_REFRESH_MINUTES = int(os.getenv("GATEWAY_CACHE_REFRESH_MINUTES", "30"))
except ValueError:
    logger.warning("Invalid GATEWAY_CACHE_REFRESH_MINUTES. Using default 30.")
    CACHE_REFRESH_MINUTES = 30
CACHE_REFRESH_INTERVAL = timedelta(minutes=CACHE_REFRESH_MINUTES)

# --- Tool Definition Cache ---
# Structure: { "server_url": {"last_updated": datetime, "tools": List[ToolDefinition]} }
tool_cache: Dict[str, Dict[str, Any]] = {}
cache_lock = asyncio.Lock() # To prevent race conditions during cache updates

async def fetch_tools_from_server(server_url: str) -> List[Dict[str, Any]]:
    """Fetches tool definitions from a given MCP server."""
    # NOTE: Actual implementation depends heavily on the `modelcontextprotocol` SDK's client capabilities.
    # Assuming a hypothetical MCPClient for demonstration.
    logger.info(f"Fetching tools from {server_url}")
    try:
        # Replace with actual MCPClient usage if available
        # async with MCPClient(server_url, timeout=5) as client:
        #     discovered_tools = await client.discover_tools() # Hypothetical method
        #     # Assuming discovered_tools are objects needing serialization
        #     tools_list = [tool.dict() for tool in discovered_tools] # Or however they are structured
        #     logger.info(f"Discovered {len(tools_list)} tools from {server_url}")
        #     return tools_list

        # --- Start Placeholder ---
        # Simulating network call and returning dummy data based on URL
        await asyncio.sleep(0.1)
        if "datetime" in server_url:
            return [
                {'name': 'get_current_time', 'description': 'Returns the current time in HH:MM:SS format.', 'input_schema': {}},
                {'name': 'get_current_date', 'description': 'Returns the current date in YYYY-MM-DD format.', 'input_schema': {}},
                {'name': 'calculate_date_difference', 'description': 'Calculates the difference between two dates...', 'input_schema': {'start_date': 'str', 'end_date': 'str', 'unit': 'str'}}, # Simplified schema
            ]
        elif "sqlite" in server_url:
            return [
                {'name': 'read_query', 'description': 'Executes a read-only (SELECT) SQL query...', 'input_schema': {'query': 'str'}},
                {'name': 'write_query', 'description': 'Executes a write (INSERT, UPDATE, DELETE) SQL query...', 'input_schema': {'query': 'str'}},
                {'name': 'create_table', 'description': 'Executes a CREATE TABLE SQL query.', 'input_schema': {'query': 'str'}},
                {'name': 'list_tables', 'description': 'Lists all tables in the database.', 'input_schema': {}},
                {'name': 'describe_table', 'description': 'Describes the schema...', 'input_schema': {'table_name': 'str'}},
                {'name': 'append_insight', 'description': "Appends a new text insight to the 'insights' table.", 'input_schema': {'insight': 'str'}},
            ]
        else:
            logger.warning(f"No placeholder tools defined for server URL: {server_url}")
            return []
        # --- End Placeholder ---

    except Exception as e:
        logger.error(f"Failed to fetch tools from {server_url}: {e}", exc_info=True)
        raise # Re-raise the exception to be caught in the update_tool_cache loop

async def update_tool_cache():
    """Periodically updates the tool definition cache."""
    server_urls = [DATETIME_SERVER_URL, SQLITE_SERVER_URL]
    while True:
        logger.info("Starting periodic tool cache update cycle.")
        async with cache_lock:
            for url in server_urls:
                try:
                    logger.debug(f"Updating cache for {url}")
                    tools = await fetch_tools_from_server(url)
                    tool_cache[url] = {
                        "last_updated": datetime.now(),
                        "tools": tools # Assuming fetch_tools returns list of dicts/ToolDefinition
                    }
                    logger.info(f"Successfully updated cache for {url} with {len(tools)} tools.")
                except Exception as e:
                    logger.error(f"Failed to update cache for {url}: {e}", exc_info=True)
                    # Optionally keep stale data or clear cache entry for this server
                    if url in tool_cache:
                        logger.warning(f"Keeping potentially stale cache data for {url} due to update failure.")
                    else:
                         tool_cache[url] = {"last_updated": None, "tools": []} # Mark as failed

        logger.info(f"Cache update cycle complete. Sleeping for {CACHE_REFRESH_INTERVAL}.")
        await asyncio.sleep(CACHE_REFRESH_INTERVAL.total_seconds())

# --- FastMCP Application ---
app = FastMCP(
    title="MCP Gateway",
    description="Orchestrates communication between clients, MCP servers, and the Ollama LLM.",
)

@app.on_event("startup")
async def startup_event():
    """Tasks to run on application startup."""
    # Initial cache population
    logger.info("Performing initial tool cache population...")
    async with cache_lock:
         for url in [DATETIME_SERVER_URL, SQLITE_SERVER_URL]:
            try:
                tools = await fetch_tools_from_server(url)
                tool_cache[url] = {"last_updated": datetime.now(), "tools": tools}
                logger.info(f"Initial cache population for {url} successful ({len(tools)} tools).")
            except Exception as e:
                logger.error(f"Initial cache population failed for {url}: {e}")
                tool_cache[url] = {"last_updated": None, "tools": []} # Mark as failed

    # Start the background cache update task
    logger.info("Starting background tool cache update task.")
    asyncio.create_task(update_tool_cache())

# --- Core Logic ---

# Shared httpx client for Ollama requests
ollama_client = httpx.AsyncClient(base_url=OLLAMA_API_BASE_URL, timeout=60.0) # Adjust timeout as needed

# Define input model for client requests (adjust based on actual client interaction)
class ClientRequest(BaseModel):
    prompt: str
    # Add other potential fields like conversation history, user ID, etc.

# Define how the Gateway handles incoming requests from an MCP client.
# This registration might differ based on FastMCP specifics.
# Assuming FastMCP routes requests to a handler function like this.
@app.handler() # Hypothetical decorator for the main request handler
async def handle_client_request(request: ClientRequest) -> Dict[str, Any]:
    """Handles incoming requests from MCP clients."""
    user_prompt = request.prompt
    logger.info(f"Received client request: '{user_prompt[:100]}...'")

    # 1. Get available tools from cache
    async with cache_lock:
        # Create a flat list of tool definitions from the cache
        # Assuming tool definitions are dicts as returned by placeholder fetch_tools_from_server
        available_tools = []
        tool_server_map: Dict[str, str] = {} # Map tool name to server URL
        for server_url, server_data in tool_cache.items():
            tools = server_data.get("tools", [])
            if tools: # Only add if tools were successfully fetched
                available_tools.extend(tools)
                for tool_def in tools:
                    tool_name = tool_def.get("name")
                    if tool_name:
                        tool_server_map[tool_name] = server_url
            else:
                 logger.warning(f"No tools available from {server_url} in cache.")

    logger.debug(f"Tools available for LLM: {[t.get('name') for t in available_tools]}")

    # 2. Format request for Ollama (Example using OpenAI-like format)
    # NOTE: Adjust this based on the specific Ollama model and its tool/function calling support.
    messages = [{"role": "user", "content": user_prompt}]
    ollama_request_payload = {
        "model": "llama3", # TODO: Make model configurable via .env
        "messages": messages,
        "stream": False, # Keep it simple for now
        # --- Tool specification (adjust format as needed) ---
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": tool.get("name"),
                    "description": tool.get("description"),
                    "parameters": tool.get("input_schema", {}), # Assuming schema is directly usable
                }
            } for tool in available_tools
        ] if available_tools else None
    }
    # Remove tools key if empty
    if not ollama_request_payload.get("tools"):
        del ollama_request_payload["tools"]

    # 3. Call Ollama API
    try:
        logger.debug(f"Sending request to Ollama: {ollama_request_payload}")
        response = await ollama_client.post("/api/chat", json=ollama_request_payload)
        response.raise_for_status() # Raise exception for 4xx/5xx errors
        ollama_response = response.json()
        logger.debug(f"Received response from Ollama: {ollama_response}")

    except httpx.RequestError as e:
        logger.error(f"Ollama request failed: {e}", exc_info=True)
        return create_error_response("OllamaConnectionError", f"Could not connect to Ollama API at {OLLAMA_API_BASE_URL}: {e}")
    except httpx.HTTPStatusError as e:
        logger.error(f"Ollama API returned error status {e.response.status_code}: {e.response.text}", exc_info=True)
        return create_error_response("OllamaAPIError", f"Ollama API error ({e.response.status_code})", details={"response": e.response.text})
    except Exception as e:
        logger.error(f"Unexpected error during Ollama call: {e}", exc_info=True)
        return create_error_response("GatewayError", f"An unexpected error occurred while contacting the LLM: {e}")

    # 4. Parse Ollama response and handle tool calls
    # NOTE: This structure depends heavily on Ollama's response format for tool calls.
    # Assuming a response structure similar to OpenAI where message content might be null
    # and a 'tool_calls' list is present if a tool should be invoked.
    response_message = ollama_response.get("message", {})
    tool_calls = response_message.get("tool_calls")

    if tool_calls:
        logger.info(f"Ollama requested tool call(s): {tool_calls}")

        # Append the assistant's message with tool calls to the conversation history
        messages.append(response_message)

        # Execute tool calls and gather results
        tool_results_for_ollama = []
        for call in tool_calls:
            # Assuming OpenAI-like structure: call['function']['name'], call['function']['arguments'], call['id']
            tool_name = call.get("function", {}).get("name")
            tool_id = call.get("id") # Needed to associate result with the call
            try:
                # Arguments might be a JSON string
                arguments_str = call.get("function", {}).get("arguments", "{}")
                arguments = json.loads(arguments_str)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse arguments for tool call {tool_id} ({tool_name}): {arguments_str}")
                result = create_error_response("ArgumentParseError", "Invalid arguments format received from LLM.")
                arguments = {} # Set empty args for execute_mcp_tool call if needed
            except Exception as e:
                 logger.error(f"Unexpected error parsing arguments for tool call {tool_id} ({tool_name}): {e}", exc_info=True)
                 result = create_error_response("ArgumentParseError", f"Unexpected error parsing arguments: {e}")
                 arguments = {}

            if not tool_name or not tool_id:
                logger.error(f"Malformed tool call received from Ollama: {call}")
                result = create_error_response("MalformedToolCall", "Received invalid tool call structure from LLM.")
            else:
                server_url = tool_server_map.get(tool_name)
                if not server_url:
                    logger.error(f"Unknown tool '{tool_name}' requested by Ollama. Not found in cache map.")
                    result = create_error_response("UnknownToolError", f"Tool '{tool_name}' is not available.")
                else:
                    # Execute the tool on the corresponding server
                    result = await execute_mcp_tool(server_url, tool_name, arguments)

            # Append the result message for Ollama
            # Ensure content is a JSON string if it's structured data/error
            content_str = json.dumps(result) if isinstance(result, dict) else str(result)
            tool_results_for_ollama.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": content_str,
            })
            logger.debug(f"Appended result for tool call {tool_id} ({tool_name}): {content_str[:100]}...")

        # Append all tool results to the message history
        messages.extend(tool_results_for_ollama)

        # 5. Make second call to Ollama with tool results
        logger.info("Sending tool results back to Ollama for final response.")
        ollama_request_payload_final = {
            "model": ollama_request_payload["model"], # Use the same model
            "messages": messages,
            "stream": False,
            # DO NOT include tools parameter in the second call
        }
        try:
            logger.debug(f"Sending final request to Ollama: {ollama_request_payload_final}")
            response_final = await ollama_client.post("/api/chat", json=ollama_request_payload_final)
            response_final.raise_for_status()
            ollama_response_final = response_final.json()
            logger.debug(f"Received final response from Ollama: {ollama_response_final}")

            final_content = ollama_response_final.get("message", {}).get("content")
            if final_content:
                 logger.info("Ollama returned final response after tool execution.")
                 final_response = {"response": final_content}
            else:
                 logger.error(f"Ollama final response missing expected content: {ollama_response_final}")
                 final_response = create_error_response("OllamaResponseError", "Received an unexpected or empty final response from Ollama after tool execution.")

        except httpx.RequestError as e:
            logger.error(f"Final Ollama request failed: {e}", exc_info=True)
            return create_error_response("OllamaConnectionError", f"Could not connect to Ollama API for final response: {e}")
        except httpx.HTTPStatusError as e:
            logger.error(f"Final Ollama API returned error status {e.response.status_code}: {e.response.text}", exc_info=True)
            return create_error_response("OllamaAPIError", f"Ollama API error on final response ({e.response.status_code})", details={"response": e.response.text})
        except Exception as e:
            logger.error(f"Unexpected error during final Ollama call: {e}", exc_info=True)
            return create_error_response("GatewayError", f"An unexpected error occurred while getting the final LLM response: {e}")

    else:
        # No tool call, return the direct response content
        final_content = response_message.get("content")
        if final_content:
            logger.info("Ollama returned direct response.")
            final_response = {"response": final_content}
        else:
            logger.error(f"Ollama response missing expected content and tool_calls: {ollama_response}")
            final_response = create_error_response("OllamaResponseError", "Received an unexpected or empty response from Ollama.")

    # 5. Return final response/error to client
    logger.info(f"Sending final response to client: {str(final_response)[:100]}...")
    return final_response

async def execute_mcp_tool(server_url: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
    """Helper function to execute a tool on a target MCP server."""
    logger.info(f"Executing tool '{tool_name}' on {server_url} with args: {arguments}")
    # NOTE: Replace with actual MCPClient implementation when available
    try:
        # --- Start Placeholder MCPClient Usage ---
        # Simulate network call and potential errors/results
        await asyncio.sleep(0.2) # Simulate network delay
        # Example: Simulate success for date/time tools
        if "get_current_time" in tool_name:
            return datetime.now().strftime("%H:%M:%S")
        elif "get_current_date" in tool_name:
            return datetime.now().strftime("%Y-%m-%d")
        # Example: Simulate potential error from DB server
        elif "read_query" in tool_name and "non_existent" in arguments.get("query", ""):
             logger.warning(f"Simulating DB error for tool '{tool_name}'")
             return create_error_response("DatabaseError", "Table 'non_existent' not found.", details={"query": arguments.get("query")})
        else:
            # Generic success placeholder
            return {"tool_result": f"Successfully executed {tool_name}", "args_received": arguments}
        # --- End Placeholder MCPClient Usage ---

        # --- Actual MCPClient Usage (Conceptual) ---
        # async with MCPClient(server_url, timeout=30) as client: # Assuming MCPClient exists
        #     result = await client.execute_tool(tool_name=tool_name, arguments=arguments) # Hypothetical method
        #     logger.info(f"Tool '{tool_name}' executed successfully via MCP.")
        #     # The result here might already be a dict/list/primitive, or a structured response object
        #     # Ensure it's serializable before returning
        #     return result
        # --- End Actual MCPClient Usage ---

    except ConnectionRefusedError: # Example specific exception
         logger.error(f"Connection refused when trying to execute tool '{tool_name}' on {server_url}")
         return create_error_response("MCPConnectionError", f"Connection refused by server at {server_url}")
    except asyncio.TimeoutError: # Example specific exception
         logger.error(f"Timeout executing tool '{tool_name}' on {server_url}")
         return create_error_response("MCPTimeoutError", f"Timeout occurred while executing tool '{tool_name}'")
    except Exception as e:
        # Catch-all for other potential MCP client errors or unexpected issues
        logger.error(f"MCP tool execution failed for '{tool_name}' on {server_url}: {e}", exc_info=True)
        return create_error_response("MCPToolExecutionError", f"Failed to execute tool '{tool_name}': {e}")


# --- Server Runner ---
if __name__ == "__main__":
    logger.info(f"Starting MCP Gateway on {HOST}:{PORT}")
    logger.info(f"Ollama API Base URL: {OLLAMA_API_BASE_URL}")
    logger.info(f"Date/Time Server URL: {DATETIME_SERVER_URL}")
    logger.info(f"SQLite Server URL: {SQLITE_SERVER_URL}")
    logger.info(f"Cache Refresh Interval: {CACHE_REFRESH_INTERVAL}")
    uvicorn.run(app, host=HOST, port=PORT)