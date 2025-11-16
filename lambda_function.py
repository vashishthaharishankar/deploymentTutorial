import json
import os
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv
from rag_pipeline import main_execution_flow
from salesforce_client import create_salesforce_lead


# Load environment variables (.env file should be in the Lambda package)
load_dotenv()


class UserLoginData(BaseModel):
    first_name: str
    last_name: str | None = None  # Optional
    email: str
    provider: str  # "google" or "microsoft"


class QueryChatModel(BaseModel):
    first_name: str
    last_name: str | None = None
    email: str
    provider: str
    user_query: str
    thread_id: str
    query_id: str


# --- Main Lambda Handler Function ---


def lambda_handler(event, context):
    """
    Main AWS Lambda handler function.
    Routes requests from API Gateway to the appropriate logic.
    """

    # Common headers for CORS (matching your FastAPI middleware)
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-Amz-Date, Authorization, X-Api-Key, X-Amz-Security-Token",
    }

    # Handle API Gateway preflight OPTIONS requests for CORS
    if event.get("httpMethod") == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": headers,
            "body": json.dumps("CORS preflight OK"),
        }

    try:
        # Get path and method from the API Gateway event
        # 'path' is for REST API Gateway, 'rawPath' for HTTP API Gateway
        path = event.get("path", event.get("rawPath"))
        http_method = event.get(
            "httpMethod", event.get("requestContext", {}).get("http", {}).get("method")
        )

        if not path or not http_method:
            raise ValueError("Could not determine path or HTTP method from event.")

        # Parse the request body
        body_str = event.get("body", "{}")
        if body_str is None:
            body_str = "{}"
        body = json.loads(body_str)

        # --- Routing Logic ---

        # Route 1: /login
        if path == "/login" and http_method == "POST":
            # Validate input data
            user = UserLoginData(**body)

            # --- Your original logic ---
            data = {
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "provider": user.provider,
            }

            # Uncomment this when your salesforce_client is ready
            try:
                result = create_salesforce_lead(data)
                data["salesforce_lead_id"] = result["salesforce_lead_id"]
                # print(result)
            except Exception as err:
                print(f"Got error in inserting salesforce lead!: {err}")

            response_data = data
            # --- End of original logic ---
            return response_data

        # Route 2: /api/chat/ask
        elif path == "/api/chat/ask" and http_method == "POST":
            # Validate input data
            data = QueryChatModel(**body)

            # --- Your original logic ---
            result = main_execution_flow(
                query=data.user_query,
            )
            response_data = {"response": result}
            # --- End of original logic ---

            return response_data

        # No route matched
        else:
            return {
                "statusCode": 404,
                "headers": headers,
                "response": json.dumps(
                    {"error": "Not Found", "path": path, "method": http_method}
                ),
            }

    # --- Error Handling ---
    except json.JSONDecodeError:
        return {
            "statusCode": 400,
            "headers": headers,
            "response": json.dumps({"error": "Invalid JSON in request body"}),
        }
    except ValidationError as e:
        # Pydantic validation error
        return {
            "statusCode": 422,  # Unprocessable Entity (common for validation errors)
            "headers": headers,
            "response": json.dumps(
                {"error": "Input validation failed", "details": e.errors()}
            ),
        }
    except Exception as e:
        # General unexpected error
        print(f"Internal server error: {e}")  # Log the error to CloudWatch
        return {
            "statusCode": 500,
            "headers": headers,
            "response": json.dumps({"error": "Internal server error", "details": str(e)}),
        }
