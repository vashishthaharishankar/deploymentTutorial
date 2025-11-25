import os
from simple_salesforce import Salesforce
from dotenv import load_dotenv

load_dotenv()


def check_lead_files(lead_id):
    sf = Salesforce(
        username=os.environ.get("SALESFORCE_USERNAME"),
        password=os.environ.get("SALESFORCE_PASSWORD"),
        security_token=os.environ.get("SALESFORCE_SECURITY_TOKEN"),
    )

    # Query the Link between Lead and File
    query = f"""
    SELECT ContentDocumentId, ContentDocument.Title, ContentDocument.FileExtension 
    FROM ContentDocumentLink 
    WHERE LinkedEntityId = '{lead_id}'
    """

    results = sf.query(query)

    print(f"--- Checking Lead: {lead_id} ---")
    if results["totalSize"] > 0:
        print(f"SUCCESS: Found {results['totalSize']} file(s) attached!")
        for record in results["records"]:
            print(f" - File Name: {record['ContentDocument']['Title']}")
            print(f" - File ID:   {record['ContentDocumentId']}")
    else:
        print("FAILURE: No files found linked to this Lead.")


if __name__ == "__main__":
    # The ID from your previous run
    check_lead_files("00Qf60000099eSTEAY")
