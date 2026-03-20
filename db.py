# -*- coding: utf-8 -*-
import logging
import os

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            port=os.getenv('DB_PORT'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            client_encoding='UTF8'
        )
        conn.cursor_factory = RealDictCursor
        logger.debug("Connected to database.")
        return conn
    except psycopg2.Error:
        logger.exception("Failed to connect to database.")
        return None
