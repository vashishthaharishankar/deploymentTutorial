import os
import base64
import requests
from urllib.parse import urlparse
from pydantic import BaseModel
from simple_salesforce import Salesforce, SalesforceGeneralError
from dotenv import load_dotenv

# --- Load environment variables ---
load_dotenv()

# --- Pydantic Model ---
class UserLoginData(BaseModel):
    first_name: str
    last_name: str | None = None
    email: str
    query: str | None = None
    response: str | None = None
    provider: str
    s3_file_url: str | None = None # Added this field

# --- Salesforce Connection ---
def get_salesforce_client():
    try:
        sf = Salesforce(
            username=os.environ.get("SALESFORCE_USERNAME"),
            password=os.environ.get("SALESFORCE_PASSWORD"),
            security_token=os.environ.get("SALESFORCE_SECURITY_TOKEN"),
        )
        print("Successfully connected to Salesforce.")
        return sf
    except Exception as e:
        print(f"Failed to connect to Salesforce: {e}")
        return None

sf = get_salesforce_client()

# --- Helper: Download and Encode File ---
def download_and_encode_s3_file(url: str):
    """
    Downloads file from S3 (public or presigned URL) and base64 encodes it.
    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        
        # Extract filename from URL
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        if not filename:
            filename = "attached_file.pdf" # Fallback

        # Encode content to Base64 (Required by Salesforce API)
        encoded_string = base64.b64encode(response.content).decode("utf-8")
        
        return filename, encoded_string
    except Exception as e:
        print(f"Error downloading S3 file: {e}")
        return None, None

# --- Main Function ---
def create_salesforce_lead(user: dict) -> dict:
    if not sf:
        raise RuntimeError("Salesforce connection not available")

    lead_last_name = user.get("last_name") or user.get("first_name")

    lead_data = {
        "FirstName": user.get("first_name"),
        "LastName": lead_last_name,
        "Email": user.get("email"),
        "Company": f"{user.get('provider', 'Unknown')} Login",
        "LeadSource": "Web"
    }

    try:
        # 1. Create the Lead
        result = sf.Lead.create(lead_data)
        lead_id = result.get("id")

        if not lead_id:
            raise RuntimeError(f"Salesforce creation failed: {result.get('errors')}")

        print(f"Lead created successfully: {lead_id}")
        
        attachment_status = "No file provided"

        # 2. Handle File Attachment if URL exists
        s3_url = user.get("s3_file_url")
        if s3_url:
            filename, b64_data = download_and_encode_s3_file(s3_url)
            
            if b64_data:
                # Create ContentVersion (The File)
                # Setting FirstPublishLocationId links it directly to the Lead immediately
                content_version = {
                    "Title": filename,
                    "PathOnClient": filename,
                    "VersionData": b64_data,
                    "FirstPublishLocationId": lead_id 
                }
                
                cv_result = sf.ContentVersion.create(content_version)
                if cv_result.get("success"):
                    attachment_status = "File attached successfully"
                    print(f"File '{filename}' attached to Lead {lead_id}")
                else:
                    attachment_status = "File upload failed"

        return {
            "message": "Lead created successfully",
            "salesforce_lead_id": lead_id,
            "file_status": attachment_status
        }

    except SalesforceGeneralError as e:
        raise RuntimeError(f"Salesforce API error: {e.content}") from e
    except Exception as e:
        raise RuntimeError(f"Unexpected error: {str(e)}") from e

# --- Execution ---
if __name__ == "__main__":
    # Example Data
    data = {
        "first_name": "shankar",
        "last_name": "Doe",
        "email": "hari.doe1@example.com",
        "provider": "google",
        "s3_file_url": "https://hiara-dev.s3.ap-south-1.amazonaws.com/KOTAK-MAHINDRA/DOLFY+GUPTA+UPDATED+RESUME+GEN-AI+DEVELOPER++DATA+SCIENTIST.pdf" 
    }
    
    try:
        result = create_salesforce_lead(data)
        print(result)
    except Exception as e:
        print(e)