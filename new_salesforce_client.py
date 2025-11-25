import os
import base64
import requests
from urllib.parse import urlparse
from pydantic import BaseModel
from simple_salesforce import Salesforce, SalesforceGeneralError
from dotenv import load_dotenv

# --- Load environment variables ---
load_dotenv()


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
    try:
        response = requests.get(url)
        response.raise_for_status()

        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        # Handle URL encoded filenames (e.g. %20 for spaces)
        from urllib.parse import unquote

        filename = unquote(filename)

        if not filename:
            filename = "attached_file.pdf"

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
        "LeadSource": "Web",
    }

    try:
        # 1. Create the Lead
        result = sf.Lead.create(lead_data)
        lead_id = result.get("id")

        if not lead_id:
            raise RuntimeError(f"Salesforce creation failed: {result.get('errors')}")

        print(f"Lead created successfully: {lead_id}")

        attachment_status = "No file provided"

        # 2. Handle File Attachment
        s3_url = user.get("s3_file_url")
        if s3_url:
            filename, b64_data = download_and_encode_s3_file(s3_url)

            if b64_data:
                # Step A: Create ContentVersion (The actual file)
                # Note: We do NOT set FirstPublishLocationId here to avoid permission issues.
                # We upload it as a private file first.
                content_version = {
                    "Title": filename,
                    "PathOnClient": filename,
                    "VersionData": b64_data,
                    "IsMajorVersion": True,
                }

                cv_result = sf.ContentVersion.create(content_version)
                cv_id = cv_result.get("id")

                if cv_result.get("success"):
                    # Step B: Query the ContentDocumentId
                    # When a ContentVersion is created, Salesforce automatically creates a ContentDocument container
                    cv_data = sf.ContentVersion.get(cv_id)
                    content_document_id = cv_data.get("ContentDocumentId")

                    # Step C: Create ContentDocumentLink (The Bridge)
                    # This explicitly links the File (ContentDocument) to the Lead (LinkedEntity)
                    cd_link = {
                        "ContentDocumentId": content_document_id,
                        "LinkedEntityId": lead_id,
                        "ShareType": "V",  # V = Viewer, I = Inferred, C = Collaborator
                        "Visibility": "AllUsers",  # Ensures internal users can see it
                    }

                    link_result = sf.ContentDocumentLink.create(cd_link)

                    if link_result.get("success"):
                        attachment_status = "File attached and linked successfully"
                        print(f"File '{filename}' linked to Lead {lead_id}")
                    else:
                        attachment_status = "File uploaded but linking failed"
                else:
                    attachment_status = "File upload failed"

        return {
            "message": "Lead created successfully",
            "salesforce_lead_id": lead_id,
            "file_status": attachment_status,
        }

    except SalesforceGeneralError as e:
        raise RuntimeError(f"Salesforce API error: {e.content}") from e
    except Exception as e:
        raise RuntimeError(f"Unexpected error: {str(e)}") from e


# --- Execution ---
if __name__ == "__main__":
    data = {
        "first_name": "shyam",
        "last_name": "mango",
        "email": "hari.doe121@example.com",
        "provider": "guest",
        # Ensure the URL is valid and accessible
        "s3_file_url": "https://hiara-dev.s3.ap-south-1.amazonaws.com/KOTAK-MAHINDRA/DOLFY+GUPTA+UPDATED+RESUME+GEN-AI+DEVELOPER++DATA+SCIENTIST.pdf",
    }

    try:
        result = create_salesforce_lead(data)
        print(result)
    except Exception as e:
        print(e)
