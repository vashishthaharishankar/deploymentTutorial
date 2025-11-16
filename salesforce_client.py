import os
from pydantic import BaseModel
from simple_salesforce import Salesforce, SalesforceGeneralError
from dotenv import load_dotenv

# --- Load environment variables ---
load_dotenv()


# --- Pydantic Model (still useful for validation) ---
class UserLoginData(BaseModel):
    first_name: str
    last_name: str | None = None
    email: str
    query: str | None = None
    response: str | None = None
    provider: str  # "google" or "microsoft"


# --- Salesforce Connection (do this once and reuse) ---
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


# --- Reusable Function ---
def create_salesforce_lead(user) -> dict:
    """
    Creates a Salesforce Lead using reusable function-based logic.
    Call this function directly without FastAPI.
    """

    if not sf:
        raise RuntimeError("Salesforce connection not available")

    # Ensure last name
    lead_last_name = user["last_name"] or user["first_name"]

    lead_data = {
        "FirstName": user["first_name"],
        "LastName": lead_last_name,
        "Email": user["email"],
        "Company": f"{user['provider']} Login",
        "LeadSource": "Web"
    }

    try:
        result = sf.Lead.create(lead_data)
        lead_id = result.get("id")

        if not lead_id:
            raise RuntimeError(f"Salesforce creation failed: {result.get('errors')}")

        print(f"Lead created successfully: {lead_id}")

        return {
            "message": "Lead created successfully",
            "salesforce_lead_id": lead_id
        }

    except SalesforceGeneralError as e:
        raise RuntimeError(f"Salesforce API error: {e.content}") from e
    except Exception as e:
        raise RuntimeError(f"Unexpected error: {str(e)}") from e


# if __name__ == "__main__":
#     # data = UserLoginData(
#     #     first_name="John",
#     #     last_name="Doe",
#     #     email="john2@example.com",
#     #     provider="google"
#     # )

#     data = {
#         "first_name": "Hari",
#         "last_name":"Doe",
#         "email":"john3@example.com",
#         "provider":"google"

#     }
#     result = create_salesforce_lead(data)
#     print(result)
