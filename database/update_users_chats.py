import datetime
import logging
from .PostgresConnection import ConnectDB


def add_user_chat(chat_data: dict):
    """
    Inserts a new chat message into the public.users_chats table.

    Args:
        chat_data (dict): A dictionary containing chat information.
                          Expected keys: 'email', 'user_query', 'thread_id', 'query_id'.
                          'first_name', 'last_name', 'provider' are ignored.

    Returns:
        dict: The response from the ConnectDB.insert() method.
    """
    db_conn = None
    try:
        insert_query = """
        INSERT INTO public.users_chats (
            email, s3_uri, user_query, bot_response, thread_id, query_id
        )
        VALUES (%s, %s, %s, %s, %s, %s);
        """

        data_tuple = (
            chat_data.get("email"),
            chat_data.get("s3_uri"),
            chat_data.get("user_query"),
            chat_data.get("bot_response"),
            chat_data.get("thread_id"),
            chat_data.get("query_id"),
        )

        query_dict = [{"query": insert_query, "data": data_tuple}]

        db_conn = ConnectDB()
        if db_conn.conn is None:
            logging.error("Failed to establish database connection.")
            return {
                "status_code": 500,
                "status": "failed",
                "message": "Failed to connect to DB.",
            }

        logging.info(f"Adding chat entry for user: {chat_data.get('email')}")
        response = db_conn.insert(query_dict)
        return response
    except Exception as e:
        logging.error(f"Error in add_user_chat: {e}")
        return {"status_code": 500, "status": "failed", "message": str(e)}
    finally:
        if db_conn:
            db_conn.close_connection()

