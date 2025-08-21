
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from psycopg2 import extras
from contextlib import contextmanager
from typing import Optional, Dict, Any, List
import logging
import phonenumbers

import json
from configs import postgres_db, postgres_userName, postgres_password, postgres_url, postgres_port

logger = logging.getLogger(__name__)

class PostgreSQL:
    """PostgreSQL database connection manager with connection pooling."""

    def __init__(self):
        """Initialize the connection pool."""
        self.connection_pool = psycopg2.pool.ThreadedConnectionPool(
            1, 5,
            database=postgres_db, 
            user=postgres_userName,
            password=postgres_password, 
            host=postgres_url, 
            port=postgres_port
        )
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = None
        try:
            conn = self.connection_pool.getconn()
            yield conn
        finally:
            if conn:
                self.connection_pool.putconn(conn)
    
    @contextmanager
    def get_cursor(self, conn, cursor_factory=None):
        """Context manager for database cursors."""
        cursor = None
        try:
            cursor = conn.cursor(cursor_factory=cursor_factory)
            yield cursor
            conn.commit()
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if cursor:
                cursor.close()
    
    def execute_query(self, sql, values, fetch_one=False, fetch_all=False, cursor_factory=None):
        """Execute a query and return results if requested."""
        with self.get_connection() as conn:
            with self.get_cursor(conn, cursor_factory) as cursor:
                cursor.execute(sql, values)
                
                if fetch_one:
                    return cursor.fetchone()
                elif fetch_all:
                    return cursor.fetchall()
                else:
                    return cursor.rowcount
    
    def insert(self, sql, values):
        """Execute insert SQL query and return the ID of the inserted row."""
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute(sql, values)
                    conn.commit()
                    row = cursor.fetchone()
                    return row[0] if row and len(row) > 0 else None
        except psycopg2.OperationalError:
            # Handle cursor closed error
            print("Cursor already closed. Retrying...")
            return self.insert(sql, values)
    
    def select_many(self, sql, values=tuple()):
        """Execute select many SQL query."""
        try:
            return self.execute_query(sql, values, fetch_all=True, cursor_factory=RealDictCursor)
        except psycopg2.OperationalError:
            # Handle cursor closed error
            print("Cursor already closed. Retrying...")
            return self.select_many(sql, values)
    
    def select_one(self, sql, values = tuple()):
        """Execute select one SQL query."""
        try:
            return self.execute_query(sql, values, fetch_one=True, cursor_factory=RealDictCursor)
        except psycopg2.OperationalError:
            # Handle cursor closed error
            print("Cursor already closed. Retrying...")
            return self.select_one(sql, values)
    
    def update_delete(self, sql, values):
        """Execute update or delete SQL query."""
        try:
            return self.execute_query(sql, values)
        except psycopg2.OperationalError:
            # Handle cursor closed error
            print("Cursor already closed. Retrying...")
            return self.update_delete(sql, values)

    def bulk_update(self, sql, values):
        """Execute bulk update SQL query."""
        with self.get_connection() as conn:
            with self.get_cursor(conn) as cursor:
                cursor.executemany(sql, values)
                conn.commit()

    def bulk_insert(self, sql, values, batch_size=500):
        """Execute bulk insert SQL query in batches."""
        with self.get_connection() as conn:
            with self.get_cursor(conn) as cursor:
                for i in range(0, len(values), batch_size):
                    batch = values[i:i + batch_size]
                    try:
                        cursor.executemany(sql, batch)
                        conn.commit()
                    except (Exception, psycopg2.DatabaseError) as batch_error:
                        print(f"Error in batch starting at index {i}: {batch_error}")
                        conn.rollback()
                        raise

    def __del__(self):
        """Close all connections in the pool when the object is destroyed."""
        if hasattr(self, 'connection_pool'):
            self.connection_pool.closeall()

# Create a singleton instance
postgreSQL = PostgreSQL()


class DatabaseService:
    
    def __init__(self):
        self.db = postgreSQL
    

    def get_or_create_user(self, whatsapp_id: str, phone_number: str, 
                          profile_name: Optional[str] = None, 
                          timezone: str = 'UTC') -> int:
        try:
            # First, try to get existing user
            select_sql = "SELECT id FROM users WHERE whatsapp_id = %s"
            
            logger.info(f"Checking for existing user with whatsapp_id: {whatsapp_id}")
            logger.debug(f"Select query: {select_sql}")
            
            result = self.db.select_one(select_sql, (whatsapp_id,))
            
            if result:
                logger.info(f"Found existing user with ID: {result['id']}")
                return result['id']
            
            # User doesn't exist, create new one
            insert_sql = """
                INSERT INTO users (whatsapp_id, phone_number, profile_name, timezone, created_at, updated_at) 
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) 
                RETURNING id
            """
            
            logger.info(f"Creating new user with whatsapp_id: {whatsapp_id}")
            logger.debug(f"Insert query: {insert_sql}")
            
            user_id = self.db.insert(insert_sql, (whatsapp_id, phone_number, profile_name, timezone))
            
            if user_id:
                logger.info(f"Created new user with ID: {user_id}")
                return user_id
            else:
                raise Exception("Failed to create user - no ID returned")
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"Error in get_or_create_user: {e}")
            raise

    def get_raw_message_by_sid(self, message_sid: str) -> Optional[Dict[str, Any]]:
        try:
            select_sql = "SELECT * FROM raw_messages WHERE message_sid = %s"
            return self.db.select_one(select_sql, (message_sid,))
        except Exception as e:
            logger.error(f"Error in get_raw_message_by_sid: {e}")
            raise

    def store_raw_message(self, user_id: int, message_sid: str, body: Optional[str],
                        message_type: str, from_number: str, to_number: str,
                        status: str = 'received', num_media: int = 0,
                        account_sid: Optional[str] = None, api_version: Optional[str] = None,
                        sms_message_sid: Optional[str] = None,
                        raw_data: Optional[Dict[str, Any]] = None) -> int:
        try:
            # Check if message already exists (idempotency check)
            existing_message = self.get_raw_message_by_sid(message_sid)
            if existing_message:
                logger.info(f"Message with SID {message_sid} already exists with ID: {existing_message['id']}")
                return existing_message['id']
            
            # Message doesn't exist, proceed with insertion
            insert_sql = """
                INSERT INTO raw_messages 
                (user_id, message_sid, sms_message_sid, body, message_type, from_number, to_number, status, num_media, account_sid, api_version, created_at, raw_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s)
                RETURNING id
            """
            
            logger.info(f"Storing new raw message for user_id: {user_id}, message_sid: {message_sid}")
            logger.debug(f"Insert query: {insert_sql}")
            
            # Convert raw_data to JSON string if provided
            raw_data_json = json.dumps(raw_data) if raw_data else None
            
            message_id = self.db.insert(
                insert_sql, 
                (user_id, message_sid, sms_message_sid, body, message_type, from_number, to_number, status, num_media, account_sid, api_version, raw_data_json)
            )
            
            if message_id:
                logger.info(f"Stored new raw message with ID: {message_id}")
                return message_id
            else:
                raise Exception("Failed to store raw message - no ID returned")
                
        except Exception as e:
            logger.error(f"Error in store_raw_message: {e}")
            raise

    def store_media_file(self, raw_message_id: int, media_sid: Optional[str],
                        content_type: Optional[str],
                        file_size: Optional[int], file_hash: Optional[str],
                        s3_key: Optional[str], s3_url: Optional[str],
                        description: Optional[str] = None) -> int:
        try:
            # Check for existing file with same hash to avoid duplicates
            existing_file = None
            if file_hash:
                select_sql = "SELECT id FROM media_files WHERE file_hash = %s"
                existing_file = self.db.select_one(select_sql, (file_hash,))
            
            if existing_file:
                logger.info(f"Media file already exists with ID: {existing_file['id']}")

                # Increment forwarded count
                update_sql = "UPDATE media_files SET forwarded_count = forwarded_count + 1 WHERE id = %s"
                self.db.update_delete(update_sql, (existing_file['id'],))

                return existing_file['id']
            else:
                # Store as new original file
                insert_sql = """
                    INSERT INTO media_files 
                    (raw_message_id, media_sid, content_type, file_size, file_hash, s3_key, s3_url, description, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING id
                """
                
                logger.info(f"Storing new media file for message_id: {raw_message_id}")
                
                media_id = self.db.insert(
                    insert_sql,
                    (raw_message_id, media_sid, content_type, file_size, file_hash, s3_key, s3_url, description)
                )
            
            if media_id:
                logger.info(f"Stored media file with ID: {media_id}")
                return media_id
            else:
                raise Exception("Failed to store media file - no ID returned")
                
        except Exception as e:
            logger.error(f"Error in store_media_file: {e}")
            raise

    def get_media_files_by_message_id(self, raw_message_id: int) -> List[Dict[str, Any]]:
        try:
            select_sql = "SELECT * FROM media_files WHERE raw_message_id = %s ORDER BY created_at"
            return self.db.select_many(select_sql, (raw_message_id,))
        except Exception as e:
            logger.error(f"Error getting media files for message {raw_message_id}: {e}")
            raise

    def get_memory_by_message_id(self, raw_message_id: int) -> Optional[Dict[str, Any]]:
        try:
            select_sql = "SELECT * FROM memories WHERE raw_message_id = %s"
            return self.db.select_one(select_sql, (raw_message_id,))
        except Exception as e:
            logger.error(f"Error in get_memory_by_message_id: {e}")
            raise

    def store_memory(self, user_id: int, raw_message_id: int, mem0_id: str, mem0_infered_memory: str) -> int:
        """Store a memory in the database. Idempotent - returns existing memory ID if duplicate."""
        try:
            # Memory doesn't exist, proceed with insertion
            insert_sql = """
                INSERT INTO memories (user_id, raw_message_id, mem0_id, mem0_infered_memory, created_at, updated_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id
            """
            memory_id = self.db.insert(insert_sql, (user_id, raw_message_id, mem0_id, mem0_infered_memory))
            logger.info(f"Stored new memory with ID: {memory_id}")
            return memory_id
        except Exception as e:
            logger.error(f"Error in store_memory: {e}")
            raise
    
    def update_memory(self, raw_message_id: int, mem0_id: str, mem0_infered_memory: str) -> int:
        try:
            update_sql = "UPDATE memories SET mem0_infered_memory = %s WHERE raw_message_id = %s and mem0_id = %s" 
            self.db.update_delete(update_sql, (mem0_infered_memory, raw_message_id, mem0_id))
            return raw_message_id
        except Exception as e:
            logger.error(f"Error in update_memory: {e}")
            raise
    
    def delete_memory(self, mem0_id):
        try:
            delete_sql = "DELETE FROM memories WHERE mem0_id = %s"
            self.db.update_delete(delete_sql, (mem0_id,))
        except Exception as e:
            logger.error(f"Error in delete_memory: {e}")
            raise

    def store_memory_direct(self, user_id: int, mem0_id: str) -> int:
        """Store a memory directly without requiring a raw message (for API-created memories)."""
        try:
            insert_sql = """
                INSERT INTO memories (user_id, raw_message_id, mem0_id, created_at, updated_at)
                VALUES (%s, NULL, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id
            """
            memory_id = self.db.insert(insert_sql, (user_id, mem0_id))
            logger.info(f"Stored new direct memory with ID: {memory_id}")
            return memory_id
        except Exception as e:
            logger.error(f"Error in store_memory_direct: {e}")
            raise

    def get_user_by_whatsapp_number(self, whatsapp_number: str) -> Optional[Dict[str, Any]]:
        """
        Get user by WhatsApp phone number (normalized to E.164).
        """
        try:
            # Remove whatsapp: prefix if present
            raw_number = whatsapp_number.replace("whatsapp:", "").strip()
            
            # Parse and normalize using phonenumbers
            parsed = phonenumbers.parse(raw_number, None)   # None → autodetect country from prefix
            clean_number = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            # e.g. "+14155551234"
            
            # DB match
            select_sql = "SELECT * FROM users WHERE phone_number = %s"
            result = self.db.select_one(select_sql, (clean_number,))
            
            return result
        except Exception as e:
            logger.error(f"Error in get_user_by_whatsapp_number: {e}")
            raise

    def get_memories_by_user_id(self, user_id: int) -> List[Dict[str, Any]]:
        try:
            select_sql = """
                SELECT m.*, rm.body as original_message_body 
                FROM memories m
                LEFT JOIN raw_messages rm ON m.raw_message_id = rm.id
                WHERE m.user_id = %s
                ORDER BY m.created_at DESC
            """
            return self.db.select_many(select_sql, (user_id,))
        except Exception as e:
            logger.error(f"Error in get_memories_by_user_id: {e}")
            raise

    def get_all_memories_with_user_info(self, user_id: int) -> List[Dict[str, Any]]:
        try:
            select_sql = """
                SELECT 
                    m.id,
                    m.user_id,
                    m.raw_message_id,
                    m.mem0_id,
                    m.created_at,
                    m.updated_at,
                    u.whatsapp_id,
                    u.phone_number,
                    u.profile_name,
                    u.timezone,
                    rm.body as original_message_body,
                    rm.message_type,
                    ARRAY_AGG(mf.s3_key) FILTER (WHERE mf.s3_key IS NOT NULL) as media_file_s3_keys
                FROM memories m
                JOIN users u ON m.user_id = u.id
                LEFT JOIN raw_messages rm ON m.raw_message_id = rm.id
                LEFT JOIN media_files mf ON rm.id = mf.raw_message_id
                WHERE m.user_id = %s
                GROUP BY m.id, m.user_id, m.raw_message_id, m.mem0_id, m.created_at, m.updated_at, u.whatsapp_id, u.phone_number, u.profile_name, u.timezone, rm.body, rm.message_type
                ORDER BY m.created_at DESC
            """
            return self.db.select_many(select_sql, (user_id,))
        except Exception as e:
            logger.error(f"Error in get_all_memories_with_user_info: {e}")
            raise

    def store_interaction(self, user_id: int, raw_message_id: int, user_message: str, bot_response: str, interaction_type: str) -> int:
        try:
            insert_sql = """
                INSERT INTO interactions (user_id, raw_message_id, user_message, bot_response, interaction_type, created_at)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING id
            """
            return self.db.insert(insert_sql, (user_id, raw_message_id, user_message, bot_response, interaction_type))
        except Exception as e:
            logger.error(f"Error in store_interaction: {e}")
            raise
    
    def get_interactions_by_user_id(self, user_id: int , limit:int = 10, detailed=False) -> List[Dict[str, Any]]:
        try:
            values = []
            if detailed:
                # detailed query with memory_id and raw_message_id and media_files if any
                select_sql = """
                    select
                        i.id,
                        i.raw_message_id,
                        i.user_message,
                        i.bot_response,
                        coalesce(rm.body, 'NO_TEXT_ONLY_MEDIA') as original_message_body,
                        rm.message_type,
                        ARRAY_AGG(mf.s3_key) filter (
                        where mf.s3_key is not null) as media_file_s3_keys,
                        array_agg(
                            json_build_object(
                                'mem0_id', m.mem0_id,
                                'mem0_infered_memory', m.mem0_infered_memory
                            ) 
                        ) filter (
                            where m.mem0_infered_memory is not null
                        ) as memories
                    from
                        interactions i
                    left join memories m on
                        m.raw_message_id = i.raw_message_id
                    left join raw_messages rm on
                        m.raw_message_id = rm.id
                    left join media_files mf on
                        rm.id = mf.raw_message_id
                    where
                        i.user_id = %s
                    group by
                        i.id,
                        i.raw_message_id,
                        i.user_message,
                        i.bot_response,
                        rm.body,
                        rm.message_type,
                        i.created_at
                    order by
                        i.id desc
                    limit %s
                """
                values = (user_id, limit)
            else:
                select_sql = "SELECT * FROM interactions WHERE user_id = %s ORDER BY id DESC LIMIT %s"
                values = (user_id, limit)

            return self.db.select_many(select_sql, values)
        except Exception as e:
            logger.error(f"Error in get_interactions_by_user_id: {e}")
            raise

    def get_media_file_by_hash(self, user_id: int, file_hash: str) -> Optional[Dict[str, Any]]:
        try:
            select_sql = "SELECT * FROM media_files WHERE user_id = %s and file_hash = %s"
            return self.db.select_one(select_sql, (user_id, file_hash,))
        except Exception as e:
            logger.error(f"Error in get_media_file_by_hash: {e}")
            raise
# Global database instance
db_service = DatabaseService()
