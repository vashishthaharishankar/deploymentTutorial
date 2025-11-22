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

load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID_1")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY_1")
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION_1", "ap-south-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "hiara-dev")

try:
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_DEFAULT_REGION,
    )
except Exception as e:
    print("Error initializing S3 client:", e)
    s3_client = None


# --------- MODELS ---------
class UserLoginData(BaseModel):
    first_name: str | None
    last_name: str | None = None
    email: str | None
    provider: str | None


class QueryChatModel(BaseModel):
    first_name: str | None
    last_name: str | None = None
    email: str | None
    provider: str | None
    user_query: str | None
    thread_id: str | None
    query_id: str | None


# --------- CORS HEADERS (GLOBAL FIX) ----------
CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "*",     # IMPORTANT FIX
    "Access-Control-Max-Age": "86400"
}


# --------- MULTIPART PARSER ----------
def parse_multipart_form_data(body: bytes, content_type: str):
    boundary = None
    for part in content_type.split(';'):
        part = part.strip()
        if part.startswith('boundary='):
            boundary = part.split('=', 1)[1].strip('"')
            break

    if not boundary:
        raise ValueError("No boundary found in Content-Type")

    boundary_bytes = f"--{boundary}".encode("utf-8")
    parts = body.split(boundary_bytes)

    result = {}

    for part in parts:
        if not part.strip() or part.strip() == b"--":
            continue

        if b"\r\n\r\n" in part:
            headers_raw, content = part.split(b"\r\n\r\n", 1)
        else:
            continue

        headers = {}
        for line in headers_raw.decode().split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        cd = headers.get("content-disposition", "")
        field_name = None
        filename = None

        for item in cd.split(";"):
            item = item.strip()
            if item.startswith("name="):
                field_name = item.split("=", 1)[1].strip('"')
            elif item.startswith("filename="):
                filename = item.split("=", 1)[1].strip('"')

        if filename:
            result["file"] = {
                "filename": filename,
                "content": content.rstrip(b"\r\n--"),
                "content_type": headers.get("content-type", "application/octet-stream"),
            }
        elif field_name:
            value = content.rstrip(b"\r\n--").decode()
            result[field_name] = value

    return result


# --------- MAIN HANDLER ----------
def lambda_handler(event, context):

    # --- FIXED GLOBAL OPTIONS HANDLER ---
    method = (
        event.get("httpMethod")
        or event.get("requestContext", {}).get("http", {}).get("method")
        or ""
    )

    if method == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "CORS OK"}),
        }

    try:
        path = event.get("path") or event.get("rawPath")
        http_method = method

        headers_dict = event.get("headers") or {}
        content_type = (
            headers_dict.get("content-type")
            or headers_dict.get("Content-Type")
            or ""
        )

        body_str = event.get("body")
        if body_str is None:
            body_str = "{}"

        is_base64 = event.get("isBase64Encoded", False)

        # Handle multipart
        if "multipart/form-data" in content_type:
            body_bytes = base64.b64decode(body_str) if is_base64 else body_str.encode()
            body = None
        else:
            if is_base64:
                body_str = base64.b64decode(body_str).decode()
            body = json.loads(body_str)

        # ---------- ROUTES ----------

        # ---- LOGIN ----
        if path == "/login" and http_method == "POST":
            user = UserLoginData(**body)

            data = user.model_dump()

            try:
                lead = create_salesforce_lead(data)
                data["salesforce_lead_id"] = lead["salesforce_lead_id"]
            except Exception as e:
                print("Salesforce error:", e)

            try:
                handle_user_login(data)
            except Exception as e:
                print("DB login error:", e)

            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(data),
            }

        # ---- CHAT ----
        if path == "/api/chat/ask" and http_method == "POST":
            data = QueryChatModel(**body)

            result = main_execution_flow(query=data.user_query)
            response = {"response": result}

            try:
                add_user_chat(
                    {
                        "email": data.email,
                        "s3_uri": None,
                        "user_query": data.user_query,
                        "bot_response": result,
                        "thread_id": data.thread_id,
                        "query_id": data.query_id,
                    }
                )
            except Exception as e:
                print("DB chat error:", e)

            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(response),
            }

        # ---- FILE UPLOAD ----
        if path == "/upload" and http_method == "POST":

            if not s3_client:
                return {
                    "statusCode": 503,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "S3 client unavailable"}),
                }

            multipart = parse_multipart_form_data(body_bytes, content_type)

            file_data = multipart.get("file")
            payload_str = multipart.get("payload")

            if not file_data or not payload_str:
                return {
                    "statusCode": 400,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "File or payload missing"}),
                }

            filename = file_data["filename"]
            content = file_data["content"]

            ext = os.path.splitext(filename)[1].lower()
            if ext not in {".pdf", ".docx", ".jpeg", ".jpg", ".png"}:
                return {
                    "statusCode": 400,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "Invalid file type"}),
                }

            s3_key = f"KOTAK-MAHINDRA/{filename}"

            s3_client.upload_fileobj(io.BytesIO(content), S3_BUCKET_NAME, s3_key)

            url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": S3_BUCKET_NAME, "Key": s3_key},
                ExpiresIn=3600,
            )

            payload = QueryChatModel(**json.loads(payload_str))

            add_user_chat(
                {
                    "email": payload.email,
                    "s3_uri": url,
                    "user_query": None,
                    "bot_response": None,
                    "thread_id": payload.thread_id,
                    "query_id": payload.query_id,
                }
            )

            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(
                    {
                        "message": "File uploaded successfully",
                        "filename": filename,
                        "s3_bucket": S3_BUCKET_NAME,
                        "s3_key": s3_key,
                        "file_url": url,
                    }
                ),
            }

        # ---- DEFAULT ----
        return {
            "statusCode": 404,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Not Found", "path": path}),
        }

    except Exception as e:
        print("Internal error:", e)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)}),
        }
