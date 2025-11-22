import json
import os
import base64
import io
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv
from rag_pipeline import main_execution_flow
from salesforce_client import create_salesforce_lead
import boto3
from botocore.exceptions import ClientError
from database.update_users import handle_user_login
from database.update_users_chats import add_user_chat


# Load environment variables (.env file should be in the Lambda package)
load_dotenv()

# Initialize S3 client
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID_1")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY_1")
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION_1", "ap-south-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "hiara-dev")

try:
    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_DEFAULT_REGION
    )
except ClientError as e:
    print(f"Error initializing S3 client: {e}")
    s3_client = None
except Exception as e:
    print(f"A general error occurred: {e}")
    s3_client = None


class UserLoginData(BaseModel):
    first_name: str | None
    last_name: str | None = None  # Optional
    email: str | None
    provider: str | None  # "google" or "microsoft"


class QueryChatModel(BaseModel):
    first_name: str | None
    last_name: str | None = None
    email: str | None
    provider: str | None
    user_query: str | None
    thread_id: str | None
    query_id: str | None


# Helper function to parse multipart/form-data
def parse_multipart_form_data(body: bytes, content_type: str):
    """
    Parse multipart/form-data body.
    Returns a dict with 'file' and 'payload' keys.
    """
    # Parse the content type to get boundary
    boundary = None
    for part in content_type.split(';'):
        part = part.strip()
        if part.startswith('boundary='):
            boundary = part.split('=', 1)[1]
            # Remove quotes if present
            boundary = boundary.strip('"')
            break
    
    if not boundary:
        raise ValueError("No boundary found in Content-Type")
    
    # Convert body to bytes if it's a string
    if isinstance(body, str):
        body = body.encode('utf-8')
    
    # Split by boundary
    boundary_bytes = f"--{boundary}".encode('utf-8')
    parts = body.split(boundary_bytes)
    
    result = {}
    
    for part in parts:
        if not part.strip() or part.strip() == b'--':
            continue
        
        # Split headers and content
        if b'\r\n\r\n' in part:
            headers_raw, content = part.split(b'\r\n\r\n', 1)
        elif b'\n\n' in part:
            headers_raw, content = part.split(b'\n\n', 1)
        else:
            continue
        
        # Parse headers
        headers = {}
        for line in headers_raw.decode('utf-8', errors='ignore').split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                headers[key.strip().lower()] = value.strip()
        
        # Get Content-Disposition
        content_disposition = headers.get('content-disposition', '')
        
        # Extract field name and filename
        field_name = None
        filename = None
        
        for item in content_disposition.split(';'):
            item = item.strip()
            if item.startswith('name='):
                field_name = item.split('=', 1)[1].strip('"')
            elif item.startswith('filename='):
                filename = item.split('=', 1)[1].strip('"')
        
        if filename:
            # This is a file
            result['file'] = {
                'filename': filename,
                'content': content.rstrip(b'\r\n--'),
                'content_type': headers.get('content-type', 'application/octet-stream')
            }
        elif field_name:
            # This is a form field
            # Remove trailing boundary markers
            content_clean = content.rstrip(b'\r\n--').rstrip()
            result[field_name] = content_clean.decode('utf-8')
    
    return result


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

        # Get content type
        headers_dict = event.get("headers", {}) or {}
        content_type = headers_dict.get("Content-Type") or headers_dict.get("content-type") or ""
        
        # Parse the request body
        body_str = event.get("body", "{}")
        if body_str is None:
            body_str = "{}"
        
        # Check if it's base64 encoded (for binary content like multipart)
        is_base64 = event.get("isBase64Encoded", False)
        body_bytes = None
        
        if "multipart/form-data" in content_type:
            # For multipart, decode if base64
            if is_base64:
                body_bytes = base64.b64decode(body_str)
            else:
                body_bytes = body_str.encode('utf-8') if isinstance(body_str, str) else body_str
            body = None  # Will be parsed separately for multipart
        else:
            # For JSON, decode if base64
            if is_base64:
                body_str = base64.b64decode(body_str).decode('utf-8')
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

            # Create Salesforce lead
            try:
                result = create_salesforce_lead(data)
                data["salesforce_lead_id"] = result["salesforce_lead_id"]
            except Exception as err:
                print(f"Got error in inserting salesforce lead!: {err}")

            # Save to database
            try:
                handle_user_login(data)
            except Exception as err:
                print(f"Got error in handle_user_login: {err}")

            response_data = data
            # --- End of original logic ---
            return {
                "statusCode": 200,
                "headers": headers,
                "body": json.dumps(response_data)
            }

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

            # Save to database
            input_data = {
                "email": data.email,
                "s3_uri": None,
                "user_query": data.user_query,
                "bot_response": response_data["response"],
                "thread_id": data.thread_id,
                "query_id": data.query_id,
            }
            try:
                add_user_chat(input_data)
            except Exception as err:
                print(f"Got error in add_user_chat: {err}")

            return {
                "statusCode": 200,
                "headers": headers,
                "body": json.dumps(response_data)
            }

        # Route 3: /upload
        elif path == "/upload" and http_method == "POST":
            if not s3_client:
                return {
                    "statusCode": 503,
                    "headers": headers,
                    "body": json.dumps({
                        "error": "S3 client is not available. Check server configuration and credentials."
                    })
                }

            ALLOWED_EXTENSIONS = {".pdf", ".docx", ".jpeg", ".jpg", ".png"}

            try:
                # Parse multipart form data
                multipart_data = parse_multipart_form_data(body_bytes, content_type)
                
                # Get file and payload
                file_data = multipart_data.get("file")
                payload_str = multipart_data.get("payload")
                
                if not file_data:
                    return {
                        "statusCode": 400,
                        "headers": headers,
                        "body": json.dumps({"error": "No file provided"})
                    }
                
                if not payload_str:
                    return {
                        "statusCode": 400,
                        "headers": headers,
                        "body": json.dumps({"error": "No payload provided"})
                    }

                filename = file_data["filename"]
                file_content = file_data["content"]
                
                # Validate file extension
                file_extension = os.path.splitext(filename)[1].lower()
                if file_extension not in ALLOWED_EXTENSIONS:
                    return {
                        "statusCode": 400,
                        "headers": headers,
                        "body": json.dumps({
                            "error": f"File type not allowed. Must be one of: {', '.join(ALLOWED_EXTENSIONS)}"
                        })
                    }

                # Upload to S3
                s3_key = "KOTAK-MAHINDRA/" + str(filename)
                
                s3_client.upload_fileobj(
                    io.BytesIO(file_content),
                    S3_BUCKET_NAME,
                    s3_key
                )

                # Generate presigned URL
                file_url = s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': S3_BUCKET_NAME, 'Key': s3_key},
                    ExpiresIn=3600
                )

                # Parse payload and save to database
                payload_data = json.loads(payload_str)
                data = QueryChatModel(**payload_data)
                
                input_data = {
                    "email": data.email,
                    "s3_uri": file_url,
                    "user_query": None,
                    "bot_response": None,
                    "thread_id": data.thread_id,
                    "query_id": data.query_id,
                }
                
                try:
                    add_user_chat(input_data)
                except Exception as err:
                    print(f"Got error in add_user_chat: {err}")

                return {
                    "statusCode": 200,
                    "headers": headers,
                    "body": json.dumps({
                        "message": "File uploaded successfully",
                        "filename": filename,
                        "s3_bucket": S3_BUCKET_NAME,
                        "s3_key": s3_key,
                        "file_url": file_url
                    })
                }

            except ClientError as e:
                print(f"S3 Upload Error: {e}")
                return {
                    "statusCode": 500,
                    "headers": headers,
                    "body": json.dumps({"error": f"Failed to upload file to S3: {e}"})
                }
            except Exception as e:
                print(f"An unexpected error occurred: {e}")
                return {
                    "statusCode": 500,
                    "headers": headers,
                    "body": json.dumps({"error": f"An unexpected error occurred during file upload: {e}"})
                }

        # Ignore root and favicon routes
        elif path in ["/", "/favicon.ico"]:
            return {
                "statusCode": 200,
                "headers": headers,
                "body": json.dumps({"message": "OK"})
            }

        # No route matched
        else:
            return {
                "statusCode": 404,
                "headers": headers,
                "body": json.dumps(
                    {"error": "Not Found", "path": path, "method": http_method}
                ),
            }

    # --- Error Handling ---
    except json.JSONDecodeError:
        return {
            "statusCode": 400,
            "headers": headers,
            "body": json.dumps({"error": "Invalid JSON in request body"}),
        }
    except ValidationError as e:
        # Pydantic validation error
        return {
            "statusCode": 422,  # Unprocessable Entity (common for validation errors)
            "headers": headers,
            "body": json.dumps(
                {"error": "Input validation failed", "details": e.errors()}
            ),
        }
    except Exception as e:
        # General unexpected error
        print(f"Internal server error: {e}")  # Log the error to CloudWatch
        return {
            "statusCode": 500,
            "headers": headers,
            "body": json.dumps({"error": "Internal server error", "details": str(e)}),
        }
