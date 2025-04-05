import logging
import os
from datetime import datetime, timedelta, date
from typing import Optional

import uvicorn
from dotenv import load_dotenv
from modelcontextprotocol import FastMCP, ToolInput, tool
from pydantic import BaseModel, Field
from enum import Enum

# Import the error utility
try:
    from mcp_common_utils.errors import create_error_response
except ImportError:
    # Define a fallback if import fails (should not happen with editable install)
    def create_error_response(error_type: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {"error": {"type": error_type, "message": message, "details": details or {}}}

# --- Project Setup ---
# Determine the root directory of the project
# Assumes this file is in /server_datetime and the root is one level up
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Load environment variables from .env file in the project root
dotenv_path = os.path.join(PROJECT_ROOT, '.env')
load_dotenv(dotenv_path=dotenv_path)

# --- Logging Setup ---
# Dynamically import the setup function from the common package
# This relies on 'common' being installed editably
try:
    from mcp_common_utils.logging_config import setup_logging
    # Setup logging for this specific component
    setup_logging("datetime-server")
except ImportError:
    print("Error: Could not import setup_logging. Make sure 'common' is installed editably (`uv add ./common --editable`).")
    # Fallback basic config if import fails
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

logger = logging.getLogger("datetime-server")

# --- Configuration ---
HOST = os.getenv("DATETIME_SERVER_HOST", "0.0.0.0")
# Ensure port is an integer
try:
    PORT = int(os.getenv("DATETIME_SERVER_PORT", "8001"))
except ValueError:
    logger.error("Invalid DATETIME_SERVER_PORT defined in .env. Using default 8001.")
    PORT = 8001

# --- FastMCP Application ---
app = FastMCP(
    title="MCP Date/Time Server",
    description="Provides tools for getting current date/time and calculating date differences.",
)

# --- Tools Implementation ---

@tool(
    name="get_current_time",
    description="Returns the current time in HH:MM:SS format.",
)
def get_current_time() -> str:
    """Gets the current time."""
    logger.info("Executing get_current_time tool.")
    now = datetime.now()
    return now.strftime("%H:%M:%S")

@tool(
    name="get_current_date",
    description="Returns the current date in YYYY-MM-DD format.",
)
def get_current_date() -> str:
    """Gets the current date."""
    logger.info("Executing get_current_date tool.")
    today = date.today()
    return today.strftime("%Y-%m-%d")

class DateDifferenceUnit(str, Enum):
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"
    YEARS = "years"

class CalculateDateDifferenceInput(BaseModel):
    start_date: str = Field(..., description="The start date in YYYY-MM-DD format.")
    end_date: str = Field(..., description="The end date in YYYY-MM-DD format.")
    unit: DateDifferenceUnit = Field(..., description="The unit for the difference (days, weeks, months, years).")

@tool(
    name="calculate_date_difference",
    description="Calculates the difference between two dates in the specified unit (days, weeks, months, or years).",
    input_model=CalculateDateDifferenceInput,
)
def calculate_date_difference(input_data: CalculateDateDifferenceInput) -> dict | str | int:
    """Calculates the difference between two dates."""
    logger.info(f"Executing calculate_date_difference with input: {input_data}")
    try:
        start = datetime.strptime(input_data.start_date, "%Y-%m-%d").date()
        end = datetime.strptime(input_data.end_date, "%Y-%m-%d").date()
    except ValueError as e:
        logger.error(f"Error parsing dates: {e}")
        return create_error_response(
            error_type="ValueError",
            message=f"Invalid date format. Please use YYYY-MM-DD. Error: {e}",
            details={"start_date": input_data.start_date, "end_date": input_data.end_date}
        )

    delta = end - start

    if input_data.unit == DateDifferenceUnit.DAYS:
        result = delta.days
    elif input_data.unit == DateDifferenceUnit.WEEKS:
        result = delta.days // 7
    elif input_data.unit == DateDifferenceUnit.MONTHS:
        # Approximate months calculation
        result = (end.year - start.year) * 12 + end.month - start.month
        # Adjust if end day is earlier than start day in the last partial month
        if end.day < start.day:
            result -= 1
    elif input_data.unit == DateDifferenceUnit.YEARS:
        result = end.year - start.year
        # Adjust if end date is earlier in the year than start date
        if (end.month, end.day) < (start.month, start.day):
            result -= 1
    else:
        # This case should ideally be prevented by Pydantic/Enum validation
        logger.error(f"Invalid unit provided: {input_data.unit}")
        return create_error_response(
            error_type="ValueError",
            message=f"Invalid unit specified: {input_data.unit}. Must be one of {list(DateDifferenceUnit)}.",
            details={"unit": input_data.unit}
        )

    logger.info(f"Calculation result: {result} {input_data.unit}")
    # Return result as a string for consistency, though int might be fine too
    return f"{result} {input_data.unit}"

# Register the tools with the FastMCP app instance
app.include_tool(get_current_time)
app.include_tool(get_current_date)
app.include_tool(calculate_date_difference)

# --- Server Runner ---
if __name__ == "__main__":
    logger.info(f"Starting Date/Time MCP Server on {HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)