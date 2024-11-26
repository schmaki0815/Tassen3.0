import os
import logging
import sqlite3
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime
from config import DB_SCHEMA

class DatabaseManager:
    SQLITE_DB_PATH = 'kunden.db'
    
    def __init__(self):
        self.db_url = os.getenv('DATABASE_URL')
        self.use_sqlite = not bool(self.db_url)
        
        if self.use_sqlite:
            logging.info("Using SQLite database")
            # Test SQLite connection
            try:
                with sqlite3.connect(self.SQLITE_DB_PATH) as conn:
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA foreign_keys = ON")
                    conn.commit()
                    logging.info("Successfully connected to SQLite database")
            except Exception as e:
                logging.error(f"SQLite connection error: {e}")
                raise
        else:
            logging.info("Using PostgreSQL database")
            # Test PostgreSQL connection
            try:
                with psycopg2.connect(self.db_url) as conn:
                    conn.autocommit = True
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT version();")
                        logging.info("Successfully connected to PostgreSQL database")
            except Exception as e:
                logging.error(f"PostgreSQL connection error: {e}")
                raise
        
        self.conn = None
        self.schema = {
            'charges': '''
                CREATE TABLE IF NOT EXISTS charges (
                    internal_id TEXT PRIMARY KEY,
                    product_name TEXT NOT NULL,
                    supplier_name TEXT,
                    color TEXT,
                    size TEXT,
                    manufacturer TEXT NOT NULL,
                    external_id TEXT,
                    batch_number TEXT UNIQUE,
                    delivery_date TEXT NOT NULL,
                    amount INTEGER NOT NULL DEFAULT 0,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP
                )
            '''
        }
        try:
            # Test database connection
            with sqlite3.connect(self.SQLITE_DB_PATH) as conn:
                cursor = conn.cursor()
                # Enable foreign keys
                cursor.execute("PRAGMA foreign_keys = ON")
                conn.commit()
                logging.info("Successfully connected to SQLite database")
        except Exception as e:
            logging.error(f"Database connection error: {e}")
            raise
            
        self._initialize_sequence_table()
        self.initialize_database()
        
    def _initialize_sequence_table(self):
        """Initialize sequence table for SQLite autoincrement simulation"""
        if self.use_sqlite:
            try:
                with sqlite3.connect(self.SQLITE_DB_PATH) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS sequences (
                            name TEXT PRIMARY KEY,
                            value INTEGER
                        )
                    """)
                    # Initialize sequences if they don't exist
                    cursor.execute("""
                        INSERT OR IGNORE INTO sequences (name, value)
                        VALUES ('batch_number', 0)
                    """)
                    conn.commit()
            except Exception as e:
                logging.error(f"Error initializing sequence table: {e}")
                raise
        else:
            try:
                conn = self.get_connection()
                try:
                    cursor = conn.cursor()
                    # Check if sequence exists
                    cursor.execute("""
                        SELECT EXISTS (
                            SELECT FROM pg_sequences
                            WHERE sequencename = 'batch_number_seq'
                        );
                    """)
                    exists = cursor.fetchone()[0]
                    
                    if not exists:
                        cursor.execute("CREATE SEQUENCE batch_number_seq")
                        logging.info("Created PostgreSQL sequence: batch_number_seq")
                    conn.commit()
                finally:
                    cursor.close()
                    conn.close()
            except Exception as e:
                logging.error(f"Error initializing PostgreSQL sequence: {e}")
                raise

    def initialize_database(self):
        try:
            if self.use_sqlite:
                with sqlite3.connect(self.SQLITE_DB_PATH) as conn:
                    cursor = conn.cursor()
                    for table, schema in DB_SCHEMA.items():
                        # Check if table exists in SQLite
                        cursor.execute("""
                            SELECT name FROM sqlite_master 
                            WHERE type='table' AND name=?;
                        """, (table,))
                        exists = cursor.fetchone() is not None
                        
                        if not exists:
                            # Use SQLite schema as is
                            cursor.execute(schema)
                            logging.info(f"Created SQLite table: {table}")
            else:
                conn = self.get_connection()
                try:
                    cursor = conn.cursor()
                    for table, schema in DB_SCHEMA.items():
                        # Check if table exists in PostgreSQL
                        cursor.execute("""
                            SELECT EXISTS (
                                SELECT FROM pg_tables
                                WHERE schemaname = 'public' 
                                AND tablename = %s
                            );
                        """, (table,))
                        exists = cursor.fetchone()[0]
                        
                        if not exists:
                            # Convert SQLite schema to PostgreSQL
                            pg_schema = schema.replace('AUTOINCREMENT', 'GENERATED ALWAYS AS IDENTITY')
                            pg_schema = pg_schema.replace('CHARACTER SET utf8', '')
                            cursor.execute(pg_schema)
                            logging.info(f"Created PostgreSQL table: {table}")
                    conn.commit()
                finally:
                    cursor.close()
                    conn.close()
        except Exception as e:
            logging.error(f"Database initialization error: {e}")
            raise

    def get_connection(self):
        """Get a database connection with proper error handling"""
        try:
            if self.use_sqlite:
                conn = sqlite3.connect(self.SQLITE_DB_PATH)
                conn.row_factory = sqlite3.Row
                return conn
            else:
                conn = psycopg2.connect(self.db_url)
                conn.cursor_factory = DictCursor
                return conn
        except Exception as e:
            logging.error(f"Database connection error: {e}")
            raise

    def get_next_sequence_value(self, sequence_name):
        """Get next value for a sequence in SQLite"""
        if not self.use_sqlite:
            return None
            
        try:
            with sqlite3.connect(self.SQLITE_DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE sequences 
                    SET value = value + 1 
                    WHERE name = ?
                    RETURNING value
                """, (sequence_name,))
                result = cursor.fetchone()
                conn.commit()
                return result[0] if result else 1
        except Exception as e:
            logging.error(f"Error getting sequence value: {e}")
            raise

    def execute_query(self, query, params=None, fetch=False, conn=None):
        """Execute a query with proper transaction handling"""
        connection_owner = conn is None
        conn = conn or self.get_connection()
        cursor = conn.cursor()
        
        try:
            if self.use_sqlite:
                # Convert PostgreSQL placeholders to SQLite
                query = query.replace('%s', '?')
                query = query.replace('ILIKE', 'LIKE')
                query = query.replace('NOW()', "datetime('now')")
                query = query.replace('CURRENT_TIMESTAMP', "datetime('now')")
                
                # Handle ON CONFLICT for SQLite
                if 'ON CONFLICT' in query.upper():
                    if 'DO UPDATE' in query.upper():
                        # Convert to SQLite's INSERT OR REPLACE
                        query = query.replace('ON CONFLICT', 'ON CONFLICT DO UPDATE SET')
                    else:
                        # Convert to SQLite's INSERT OR IGNORE
                        query = query.replace('ON CONFLICT', 'ON CONFLICT DO NOTHING')
            else:
                # Convert SQLite syntax to PostgreSQL if needed
                query = query.replace('?', '%s')
                query = query.replace("datetime('now')", 'NOW()')
                
                # Handle SQLite's AUTOINCREMENT
                query = query.replace('AUTOINCREMENT', 'GENERATED ALWAYS AS IDENTITY')
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            if fetch:
                result = cursor.fetchall()
                if connection_owner:
                    conn.commit()
                return result if result else []
            else:
                if connection_owner:
                    conn.commit()
                return None
        except Exception as e:
            if connection_owner:
                conn.rollback()
            logging.error(f"Query execution error: {str(e)}\nQuery: {query}\nParams: {params}")
            raise
        finally:
            cursor.close()
            if connection_owner:
                conn.close()

    def execute_many(self, query, params_list):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            try:
                if self.use_sqlite:
                    # Convert PostgreSQL placeholders to SQLite
                    query = query.replace('%s', '?')
                else:
                    # Ensure PostgreSQL syntax
                    query = query.replace('?', '%s')
                
                cursor.executemany(query, params_list)
                conn.commit()
            finally:
                cursor.close()
                conn.close()
        except Exception as e:
            logging.error(f"Database bulk operation error: {e}")
            raise

db = DatabaseManager()
