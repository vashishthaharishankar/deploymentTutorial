import datetime
import logging
from .PostgresConnection import ConnectDB


def handle_user_login(user_data: dict):
    """
    Inserts a new user or updates the last_login_at timestamp if the user (email) already exists.

    Args:
        user_data (dict): A dictionary containing user information from the /login API.
                          Expected keys: 'first_name', 'last_name', 'email',
                                         'provider', 'salesforce_lead_id'.

    Returns:
        dict: The response from the ConnectDB.insert() method.
    """
    # Get the current time for 'last_login_at' and 'updated_at'
    now = datetime.datetime.now()

    # This is the "UPSERT" query.
    # It attempts to INSERT a new row.
    # If a conflict occurs on the 'email' (which has a UNIQUE constraint),
    # it instead performs an UPDATE on the existing row.
    upsert_query = """
    INSERT INTO public.users (
        first_name, last_name, email, provider, salesforce_lead_id, 
        last_login_at, created_at, updated_at
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (email)
    DO UPDATE SET
        last_login_at = %s,
        -- Optionally update other fields if they log in via a different provider, etc.
        first_name = %s,
        last_name = %s,
        provider = %s
    """

    # Prepare the data for the parameterized query
    # Note: The parameters are provided in order for VALUES, then for DO UPDATE.
    data_tuple = (
        user_data.get("first_name"),
        user_data.get("last_name"),
        user_data.get("email"),
        user_data.get("provider"),
        user_data.get("salesforce_lead_id", "sample"),
        now,  # last_login_at (for new insert)
        now,  # created_at (for new insert)
        now,  # updated_at (for new insert)
        now,  # last_login_at (for update on conflict)
        # We also update the other fields in case they changed
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

        logging.info(f"Handling login for user: {user_data.get('email')}")
        response = db_conn.insert(query_dict)
        return response
    except Exception as e:
        logging.error(f"Error in handle_user_login: {e}")
        return {"status_code": 500, "status": "failed", "message": str(e)}
    finally:
        if db_conn:
            db_conn.close_connection()

