import datetime
import logging
from .PostgresConnection import ConnectDB

# --- Helper function for fetching existing lead ID ---
import logging
# Assuming ConnectDB and its required imports are available in the scope
from .PostgresConnection import ConnectDB 
# Also assuming the provided db.fetch is the method of ConnectDB

def _fetch_existing_salesforce_lead_id(email: str):
    """
    Fetches the salesforce_lead_id for a given email from the users table 
    using a parameterized SELECT query.

    Args:
        email (str): The user's email address.

    Returns:
        str or None: The salesforce_lead_id if found, otherwise None.
    """
    db_conn = None
    try:
        db_conn = ConnectDB()
        
        if db_conn.conn is None:
             logging.error("Failed to establish database connection in _fetch_existing_salesforce_lead_id.")
             return None
             
        quoted_email = f"'{email}'" 
        
        select_query = f"SELECT salesforce_lead_id FROM public.users WHERE email = {quoted_email};"
        # --- END SECURE QUERY CONSTRUCTION ---
        
        logging.debug(f"Executing fetch query: {select_query}")
        
        # Call the provided fetch method
        fetch_response = db_conn.fetch(select_query)
        
        # The structure of the response is guaranteed by the provided db.fetch:
        # {"status_code": 200, "status": "success", "data": result, "message": "..."}
        if fetch_response.get("status_code") == 200 and fetch_response.get("data"):
            # 'data' is a list of dictionaries, e.g., [{'salesforce_lead_id': '003...'}]
            result_list = fetch_response["data"]
            
            if result_list:
                # Get the first record (there should only be one for a unique email)
                first_record = result_list[0]
                
                # Directly access the salesforce_lead_id key (reliable because db.fetch returns dicts)
                salesforce_lead_id = first_record.get('salesforce_lead_id')
                
                return salesforce_lead_id
        
        # If status wasn't 200 or no data was returned
        return None
        
    except Exception as e:
        # If an error occurs during connection, query execution, or parsing
        logging.error(f"Error fetching existing salesforce_lead_id for {email}: {e}")
        return None
        
    finally:
        if db_conn:
            db_conn.close_connection()


def handle_user_login(user_data: dict):
    """
    Inserts a new user or updates the last_login_at timestamp if the user (email) already exists.
    If 'salesforce_lead_id' is missing in the payload, it attempts to fetch the existing one from the DB.

    Args:
        user_data (dict): A dictionary containing user information from the /login API.
                          Expected keys: 'first_name', 'last_name', 'email',
                                         'provider', 'salesforce_lead_id' (optional).

    Returns:
        dict: The response from the ConnectDB.insert() method, augmented with the salesforce_lead_id.
    """
    email = user_data.get("email")
    if not email:
        return {"status_code": 400, "status": "failed", "message": "Email is required."}

    # 1. Determine the salesforce_lead_id to use
    salesforce_lead_id = user_data.get("salesforce_lead_id")
    
    if not salesforce_lead_id:
        logging.info(f"salesforce_lead_id not in payload for {email}. Attempting to fetch existing one.")
        
        # 2. Fetch existing ID if not provided in the payload
        existing_id = _fetch_existing_salesforce_lead_id(email)
        
        if existing_id:
            salesforce_lead_id = existing_id
            logging.info(f"Found existing salesforce_lead_id: {salesforce_lead_id} for {email}.")
        else:
            # If still missing, set to None or a default if your DB schema requires it.
            # Using None allows the DB to use its default or accept NULL.
            salesforce_lead_id = None
            logging.info(f"No existing salesforce_lead_id found for {email}. Will insert/update with NULL.")

    # Get the current time for 'last_login_at' and 'updated_at'
    now = datetime.datetime.now()

    # --- UPSERT QUERY ---
    # The query attempts to INSERT a new row.
    # If a conflict occurs on 'email', it performs an UPDATE on the existing row.
    upsert_query = """
    INSERT INTO public.users (
        first_name, last_name, email, provider, salesforce_lead_id, 
        last_login_at, created_at, updated_at
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (email)
    DO UPDATE SET
        last_login_at = %s,
        -- We update the salesforce_lead_id only if the incoming value is NOT NULL (or provided).
        -- Otherwise, we keep the existing one.
        salesforce_lead_id = COALESCE(%s, public.users.salesforce_lead_id), 
        first_name = %s,
        last_name = %s,
        provider = %s
    RETURNING salesforce_lead_id; -- Crucial for returning the ID used/kept
    """
    
    # Prepare the data for the parameterized query
    # Note: The parameters are provided in order for VALUES, then for DO UPDATE.
    data_tuple = (
        user_data.get("first_name"),
        user_data.get("last_name"),
        email,
        user_data.get("provider"),
        # Value for INSERT: Use the determined ID (fetched or from payload)
        salesforce_lead_id, 
        now,  # last_login_at (for new insert)
        now,  # created_at (for new insert)
        now,  # updated_at (for new insert)
        
        # Values for DO UPDATE SET:
        now,  # last_login_at (for update on conflict)
        # Value for UPDATE: Use the determined ID, COALESCE handles keeping the old value if the new one is None
        salesforce_lead_id, 
        user_data.get("first_name"),
        user_data.get("last_name"),
        user_data.get("provider"),
    )

    # Format the query for the ConnectDB.insert() method
    query_dict = [{"query": upsert_query, "data": data_tuple}]

    db_conn = None
    try:
        db_conn = ConnectDB()
        if db_conn.conn is None:
            logging.error("Failed to establish database connection.")
            return {
                "status_code": 500,
                "status": "failed",
                "message": "Failed to connect to DB.",
            }

        logging.info(f"Handling login for user: {email}")
        
        # Assuming db_conn.insert() now returns the result including the RETURNING clause data.
        # It should return a dictionary with status, message, and a 'records' key (or similar).
        response = db_conn.insert(query_dict)

        # 3. Augment the response with the determined salesforce_lead_id
        # We try to get the ID from the result of the UPSERT (RETURNING clause) first.
        # If 'response' has a 'records' key, we assume the RETURNING value is in there.
        returned_id = None
        if response.get("records") and response["records"][0]:
            # Assuming 'records' contains a list of results from the RETURNING clause, 
            # and the first element is the salesforce_lead_id
            # Example structure: [{'salesforce_lead_id': 'XYZ'}]
            if isinstance(response["records"][0], dict):
                 returned_id = response["records"][0].get("salesforce_lead_id")
            elif isinstance(response["records"][0], (list, tuple)):
                 # Assuming it's the first element in the tuple/list if not a dict
                 returned_id = response["records"][0][0] 
        
        # Use the returned ID if successful, otherwise fall back to the one we determined earlier
        final_salesforce_lead_id = returned_id if returned_id is not None else salesforce_lead_id
        
        # Augment the final response JSON
        response["salesforce_lead_id"] = final_salesforce_lead_id
        
        return response
    except Exception as e:
        logging.error(f"Error in handle_user_login: {e}")
        return {"status_code": 500, "status": "failed", "message": str(e)}
    finally:
        if db_conn:
            db_conn.close_connection()
