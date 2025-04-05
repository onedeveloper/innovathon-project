from typing import Dict, Any, Optional

def create_error_response(
    error_type: str,
    message: str,
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Creates a standardized dictionary structure for error responses.

    Args:
        error_type: A short string indicating the type of error (e.g., 'ValueError', 'ToolExecutionError', 'DatabaseError').
        message: A human-readable description of the error.
        details: An optional dictionary for additional context or technical details.

    Returns:
        A dictionary representing the structured error.
    """
    error_payload = {
        "error": {
            "type": error_type,
            "message": message,
        }
    }
    if details:
        error_payload["error"]["details"] = details
    return error_payload

# Example Usage (can be removed later):
if __name__ == '__main__':
    value_error = create_error_response(
        error_type="ValueError",
        message="Invalid date format provided.",
        details={"input_date": "31-12-2023", "expected_format": "YYYY-MM-DD"}
    )
    print(value_error)

    db_error = create_error_response(
        error_type="DatabaseError",
        message="Failed to execute query.",
        details={"query": "SELECT * FROM non_existent_table"}
    )
    print(db_error)

    generic_error = create_error_response(
        error_type="ToolExecutionError",
        message="An unexpected error occurred."
    )
    print(generic_error)