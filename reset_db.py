import logging

from db import get_db_connection

logger = logging.getLogger(__name__)

def reset_database():
    conn = get_db_connection()
    if not conn:
        print("Failed to connect to database.")
        return

    try:
        cur = conn.cursor()

        print("Dropping all tables...")
        cur.execute("""
            DROP SCHEMA public CASCADE;
            CREATE SCHEMA public;
            GRANT ALL ON SCHEMA public TO public;
            COMMENT ON SCHEMA public IS 'Standard public schema';
        """)
        
        with open('schema.sql', 'r', encoding='utf-8') as f:
            schema_sql = f.read()
            
        cur.execute(schema_sql)
        conn.commit()

        print("Database reset successfully!")
        
    except Exception:
        logger.exception("Database reset failed.")
        print("Error resetting database. Check logs for details.")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    reset_database()
