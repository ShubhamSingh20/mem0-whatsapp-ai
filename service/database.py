
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
from models.models import MediaFile, RawMessage, User, Memory

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
                          timezone: str = 'UTC') -> User:
        try:
            # First, try to get existing user
            select_sql = "SELECT * FROM users WHERE whatsapp_id = %s"
            
            result = self.db.select_one(select_sql, (whatsapp_id,))
            
            if result:
                return User(**dict(result))
            
            # User doesn't exist, create new one
            insert_sql = """
                INSERT INTO users (whatsapp_id, phone_number, profile_name, timezone, created_at, updated_at) 
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) 
                RETURNING id
            """
            
            user = self.db.insert(insert_sql, (whatsapp_id, phone_number, profile_name, timezone))
            
            if user:
                return User(**dict(self.db.select_one(f"SELECT * FROM users WHERE id = {user}", ())))
            else:
                raise Exception("Failed to create user - no ID returned")
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"Error in get_or_create_user: {e}")
            raise

    def get_raw_message_by_sid(self, message_sid: str) -> Optional[RawMessage]:
        try:
            select_sql = "SELECT * FROM raw_messages WHERE message_sid = %s"
            result = self.db.select_one(select_sql, (message_sid,))
            return RawMessage(**dict(result)) if result else None
        except Exception as e:
            logger.error(f"Error in get_raw_message_by_sid: {e}")
            raise

    def store_raw_message(self, user_id: int, message_sid: str, body: Optional[str],
                        message_type: str, from_number: str, to_number: str,
                        status: str = 'received', num_media: int = 0,
                        account_sid: Optional[str] = None, api_version: Optional[str] = None,
                        sms_message_sid: Optional[str] = None,
                        raw_data: Optional[Dict[str, Any]] = None) -> RawMessage:
        try:
            # Check if message already exists (idempotency check)
            existing_message = self.get_raw_message_by_sid(message_sid)
            if existing_message:
                return existing_message
            
            # Message doesn't exist, proceed with insertion
            insert_sql = """
                INSERT INTO raw_messages 
                (user_id, message_sid, sms_message_sid, body, message_type, from_number, to_number, status, num_media, account_sid, api_version, created_at, raw_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s)
                RETURNING id
            """
            
            logger.debug(f"Insert query: {insert_sql}")
            
            # Convert raw_data to JSON string if provided
            raw_data_json = json.dumps(raw_data) if raw_data else None
            
            message_id = self.db.insert(
                insert_sql, 
                (user_id, message_sid, sms_message_sid, body, message_type, from_number, to_number, status, num_media, account_sid, api_version, raw_data_json)
            )

            result = self.db.select_one(f"SELECT * FROM raw_messages WHERE id = {message_id}", ())
            return RawMessage(**dict(result)) if result else None
            
        except Exception as e:
            logger.error(f"Error in store_raw_message: {e}")
            raise

    def store_media_file(self, media_sid: Optional[str],
                        content_type: Optional[str],
                        file_size: Optional[int], file_hash: Optional[str],
                        s3_key: Optional[str], s3_url: Optional[str],
                        description: Optional[str] = None):
        try:
            insert_sql = """
                INSERT INTO media_files 
                (media_sid, content_type, file_size, file_hash, s3_key, s3_url, description, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING id
            """

            media_file = self.db.insert(
                insert_sql,
                (media_sid, content_type, file_size, file_hash, s3_key, s3_url, description)
            )

            return MediaFile(**dict(self.db.select_one(f"SELECT * FROM media_files WHERE id = {media_file}", ())))
            
        except Exception as e:
            logger.error(f"Error in store_media_file: {e}")
            raise
    
    def associate_media_with_message(self, raw_message_id: int, media_file_id: int):
        """Associate a media file with a message through the pivot table."""
        try:
            insert_sql = """
                INSERT INTO message_media (raw_message_id, media_file_id, created_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (raw_message_id, media_file_id) DO NOTHING
                RETURNING id
            """
            
            self.db.insert(insert_sql, (raw_message_id, media_file_id))
                
        except Exception as e:
            logger.error(f"Error in associate_media_with_message: {e}")
            raise

    def get_media_files_by_message_id(self, raw_message_id: int) -> List[Dict[str, Any]]:
        """Get all media files associated with a message via the pivot table."""
        try:
            select_sql = """
                SELECT mf.* 
                FROM media_files mf
                INNER JOIN message_media mm ON mf.id = mm.media_file_id
                WHERE mm.raw_message_id = %s 
                ORDER BY mm.created_at
            """
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
            return memory_id
        except Exception as e:
            logger.error(f"Error in store_memory: {e}")
            raise
    
    def update_memory(self, raw_message_id: int, mem0_id: str, mem0_infered_memory: str) -> int:
        try:
            update_sql = "UPDATE memories SET mem0_infered_memory = %s WHERE mem0_id = %s" 
            self.db.update_delete(update_sql, (mem0_infered_memory, mem0_id))
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

    def increment_forwarded_count(self, media_file_id: int):
        try:
            update_sql = "UPDATE media_files SET forwarded_count = forwarded_count + 1 WHERE id = %s"
            self.db.update_delete(update_sql, (media_file_id,))
        except Exception as e:
            logger.error(f"Error in increment_forwarded_count: {e}")
            raise

    def list_memories(self, user_id: int) -> List[Memory]:
        try:
            select_sql = """
                SELECT * FROM memories
                WHERE user_id = %s
                ORDER BY created_at DESC
            """
            result = self.db.select_many(select_sql, (user_id,))
            return result
        except Exception as e:
            logger.error(f"Error in list_memories: {e}")
            raise

    def get_all_memories_with_user_info(self, user_id: int) -> List[Dict[str, Any]]:
        try:
            select_sql = """
                SELECT
                rm.id                              AS raw_message_id,
                rm.body                            AS original_message_body,
                rm.message_type,
                rm.created_at                      AS message_created_at,
                media.media_file_s3_keys,
                COALESCE(mem.memories, '[]'::json) AS memories
                FROM raw_messages rm
                JOIN LATERAL (
                SELECT json_agg(
                        json_build_object(
                            'id', m.id,
                            'mem0_id', m.mem0_id,
                            'mem0_infered_memory', m.mem0_infered_memory,
                            'created_at', m.created_at,
                            'updated_at', m.updated_at
                        )
                        ORDER BY m.created_at DESC
                        ) AS memories
                FROM memories m
                WHERE m.raw_message_id = rm.id
                ) mem ON TRUE
                -- media files tied to this message (not to memories)
                LEFT JOIN LATERAL (
                SELECT array_agg(DISTINCT mf.s3_key)
                        FILTER (WHERE mf.s3_key IS NOT NULL) AS media_file_s3_keys
                FROM message_media mm
                JOIN media_files mf ON mf.id = mm.media_file_id
                WHERE mm.raw_message_id = rm.id
                ) media ON TRUE
                -- optional: restrict to a specific user (keeps only messages that produced memories for that user)
                WHERE EXISTS (
                SELECT 1
                FROM memories m2
                WHERE m2.raw_message_id = rm.id
                    AND m2.user_id = %s
                )
                ORDER BY rm.created_at DESC;

            """
            return self.db.select_many(select_sql, (user_id,))
        except Exception as e:
            logger.error(f"Error in get_all_memories_with_user_info: {e}")
            raise

    def get_sourced_memories(self, user_id: int) -> List[Dict[str, Any]]:
        try:
            select_sql = """
                SELECT * FROM memories WHERE user_id = %s and raw_message_id isnull
                ORDER BY created_at DESC
            """
            return self.db.select_many(select_sql, (user_id,))
        except Exception as e:
            logger.error(f"Error in get_sourced_memories: {e}")
            raise

    def store_interaction(self, user_id: int, raw_message_id: int, user_message: str, bot_response: str, interaction_type: str, sources: Optional[List[str]] = None) -> int:
        try:
            insert_sql = """
                INSERT INTO interactions (user_id, raw_message_id, user_message, bot_response, interaction_type, sources, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING id
            """
            return self.db.insert(insert_sql, (user_id, raw_message_id, user_message, bot_response, interaction_type, sources))
        except Exception as e:
            logger.error(f"Error in store_interaction: {e}")
            raise
    
    def get_interaction_by_message_id(self, raw_message_id: int) -> Dict[str, Any]:
        try:
            select_sql = "SELECT * FROM interactions WHERE raw_message_id = %s"
            return self.db.select_one(select_sql, (raw_message_id,))
        except Exception as e:
            logger.error(f"Error in get_interaction_by_message_id: {e}")
            raise   

    def get_interactions_by_user_id(self, user_id: int , limit:int = 10, detailed=False) -> List[Dict[str, Any]]:
        try:
            values = []
            if detailed:
                # detailed query with memory_id and raw_message_id and media_files if any
                select_sql = """
                    SELECT
                    i.id,
                    i.user_id,
                    i.raw_message_id,
                    i.user_message,
                    i.bot_response,
                    i.sources AS sources,
                    COALESCE(rm.body, 'NO_TEXT_ONLY_MEDIA') AS original_message_body,
                    rm.message_type,
                    media.media_file_s3_keys,
                    COALESCE(mem_created.memory_created, '[]'::json) AS memory_created
                    FROM interactions i
                    LEFT JOIN raw_messages rm
                    ON rm.id = i.raw_message_id

                    -- Aggregate media keys for this raw_message once
                    LEFT JOIN LATERAL (
                    SELECT array_agg(DISTINCT mf.s3_key)
                            FILTER (WHERE mf.s3_key IS NOT NULL) AS media_file_s3_keys
                    FROM message_media mm
                    JOIN media_files mf ON mf.id = mm.media_file_id
                    WHERE mm.raw_message_id = i.raw_message_id
                    ) media ON TRUE

                    LEFT JOIN LATERAL (
                    SELECT json_agg(
                            json_build_object(
                                'id', m.id,
                                'mem0_id', m.mem0_id,
                                'mem0_infered_memory', m.mem0_infered_memory,
                                'created_at', m.created_at,
                                'updated_at', m.updated_at
                            )
                            ORDER BY m.created_at DESC
                            ) AS memory_created
                    FROM memories m
                    WHERE m.raw_message_id = i.raw_message_id
                    ) mem_created ON TRUE

                    WHERE i.user_id = %s
                    ORDER BY i.id DESC
                    LIMIT %s;

                """
                values = (user_id, limit)
            else:
                select_sql = "SELECT * FROM interactions WHERE user_id = %s ORDER BY id DESC LIMIT %s"
                values = (user_id, limit)

            return self.db.select_many(select_sql, values)
        except Exception as e:
            logger.error(f"Error in get_interactions_by_user_id: {e}")
            raise

    def get_media_file_by_hash(self, file_hash: str) -> Optional[MediaFile]:
        try:
            select_sql = "SELECT * FROM media_files WHERE file_hash = %s"
            result = self.db.select_one(select_sql, (file_hash,))
            return MediaFile(**dict(result)) if result else None
        except Exception as e:
            logger.error(f"Error in get_media_file_by_hash: {e}")
            raise

    # Analytics Methods
    def get_analytics_summary(self) -> Dict[str, Any]:
        """Get comprehensive analytics summary"""
        try:
            return {
                "summary": self._get_summary_stats(),
                "user_analytics": self._get_user_analytics(),
                "memory_analytics": self._get_memory_analytics(),
                "media_analytics": self._get_media_analytics(),
                "interaction_analytics": self._get_interaction_analytics()
            }
        except Exception as e:
            logger.error(f"Error in get_analytics_summary: {e}")
            raise

    def _get_summary_stats(self) -> Dict[str, Any]:
        """Get basic summary statistics"""
        try:
            summary_sql = """
                SELECT 
                    (SELECT COUNT(*) FROM users WHERE is_active = true) as total_users,
                    (SELECT COUNT(*) FROM memories) as total_memories,
                    (SELECT COUNT(*) FROM interactions) as total_interactions,
                    (SELECT COUNT(*) FROM raw_messages) as total_messages,
                    (SELECT COUNT(*) FROM media_files) as total_media_files
            """
            result = self.db.select_one(summary_sql)
            return dict(result) if result else {}
        except Exception as e:
            logger.error(f"Error in _get_summary_stats: {e}")
            raise

    def _get_user_analytics(self) -> Dict[str, Any]:
        try:
            # New users this week and month
            new_users_sql = """
                SELECT 
                    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') as new_users_this_week,
                    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '30 days') as new_users_this_month
                FROM users
            """
            new_users_result = self.db.select_one(new_users_sql)

            # Most active users (by message count)
            active_users_sql = """
                SELECT 
                    u.whatsapp_id,
                    u.profile_name,
                    COUNT(rm.id) as message_count,
                    COUNT(DISTINCT DATE(rm.created_at)) as active_days
                FROM users u
                LEFT JOIN raw_messages rm ON u.id = rm.user_id
                WHERE u.is_active = true
                GROUP BY u.id, u.whatsapp_id, u.profile_name
                HAVING COUNT(rm.id) > 0
                ORDER BY message_count DESC
                LIMIT 10
            """
            active_users = self.db.select_many(active_users_sql)

            # Timezone distribution
            timezone_sql = """
                SELECT timezone, COUNT(*) as user_count
                FROM users 
                WHERE is_active = true 
                GROUP BY timezone 
                ORDER BY user_count DESC
            """
            timezone_dist = self.db.select_many(timezone_sql)

            return {
                "new_users_this_week": new_users_result['new_users_this_week'] if new_users_result else 0,
                "new_users_this_month": new_users_result['new_users_this_month'] if new_users_result else 0,
                "most_active_users": [dict(row) for row in active_users] if active_users else [],
                "timezone_distribution": {row['timezone']: row['user_count'] for row in timezone_dist} if timezone_dist else {}
            }
        except Exception as e:
            logger.error(f"Error in _get_user_analytics: {e}")
            raise

    def _get_memory_analytics(self) -> Dict[str, Any]:
        try:
            # Memory creation stats
            memory_creation_sql = """
                SELECT 
                    COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE) as memories_created_today,
                    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') as memories_created_this_week,
                    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '30 days') as memories_created_this_month
                FROM memories
            """
            memory_creation = self.db.select_one(memory_creation_sql)

            # Most frequently sourced memories (from interactions.sources)
            frequent_sources_sql = """
                SELECT 
                    unnest(sources) as mem0_id,
                    COUNT(*) as usage_count
                FROM interactions 
                WHERE sources IS NOT NULL AND array_length(sources, 1) > 0
                GROUP BY unnest(sources)
                ORDER BY usage_count DESC
                LIMIT 10
            """
            frequent_sources = self.db.select_many(frequent_sources_sql)

            # Get memory details for the most frequent sources
            if frequent_sources:
                mem0_ids = [row['mem0_id'] for row in frequent_sources]
                placeholders = ','.join(['%s'] * len(mem0_ids))
                memory_details_sql = f"""
                    SELECT mem0_id, mem0_infered_memory, user_id
                    FROM memories 
                    WHERE mem0_id IN ({placeholders})
                """
                memory_details = self.db.select_many(memory_details_sql, tuple(mem0_ids))
                
                # Combine usage count with memory details
                memory_detail_map = {row['mem0_id']: row for row in memory_details}
                frequent_memories = []
                for source in frequent_sources:
                    mem0_id = source['mem0_id']
                    if mem0_id in memory_detail_map:
                        memory_info = memory_detail_map[mem0_id]
                        frequent_memories.append({
                            "mem0_id": mem0_id,
                            "usage_count": source['usage_count'],
                            "memory_text": memory_info['mem0_infered_memory'],
                            "user_id": memory_info['user_id']
                        })
            else:
                frequent_memories = []

            # Average memories per user
            avg_memories_sql = """
                SELECT AVG(memory_count) as avg_memories_per_user
                FROM (
                    SELECT user_id, COUNT(*) as memory_count
                    FROM memories
                    GROUP BY user_id
                ) user_memory_counts
            """
            avg_memories = self.db.select_one(avg_memories_sql)

            return {
                "memories_created_today": memory_creation['memories_created_today'] if memory_creation else 0,
                "memories_created_this_week": memory_creation['memories_created_this_week'] if memory_creation else 0,
                "memories_created_this_month": memory_creation['memories_created_this_month'] if memory_creation else 0,
                "most_frequently_sourced": frequent_memories,
                "avg_memories_per_user": float(avg_memories['avg_memories_per_user']) if avg_memories and avg_memories['avg_memories_per_user'] else 0.0
            }
        except Exception as e:
            logger.error(f"Error in _get_memory_analytics: {e}")
            raise

    def _get_media_analytics(self) -> Dict[str, Any]:
        try:
            # Most forwarded images
            forwarded_media_sql = """
                SELECT 
                    content_type,
                    forwarded_count,
                    file_size,
                    description,
                    s3_url,
                    created_at
                FROM media_files 
                WHERE forwarded_count > 0
                ORDER BY forwarded_count DESC
                LIMIT 10
            """
            forwarded_media = self.db.select_many(forwarded_media_sql)

            # Media type distribution
            media_type_sql = """
                SELECT content_type, COUNT(*) as count
                FROM media_files
                GROUP BY content_type
                ORDER BY count DESC
            """
            media_types = self.db.select_many(media_type_sql)

            # Storage statistics
            storage_sql = """
                SELECT 
                    COUNT(*) as total_files,
                    SUM(file_size) as total_bytes
                FROM media_files
                WHERE file_size IS NOT NULL
            """
            storage_stats = self.db.select_one(storage_sql)

            total_storage_mb = 0.0
            if storage_stats and storage_stats['total_bytes']:
                total_storage_mb = float(storage_stats['total_bytes']) / (1024 * 1024)

            return {
                "most_duplicate_uploaded": [dict(row) for row in forwarded_media] if forwarded_media else [],
                "media_type_distribution": {row['content_type']: row['count'] for row in media_types} if media_types else {},
                "total_storage_mb": round(total_storage_mb, 2),
                "total_media_files": storage_stats['total_files'] if storage_stats else 0,
            }
        except Exception as e:
            logger.error(f"Error in _get_media_analytics: {e}")
            raise

    def _get_interaction_analytics(self) -> Dict[str, Any]:
        try:
            # Interaction counts
            interaction_counts_sql = """
                SELECT 
                    COUNT(*) as total_interactions,
                    COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE) as interactions_today,
                    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') as interactions_this_week
                FROM interactions
            """
            interaction_counts = self.db.select_one(interaction_counts_sql)

            # Interaction type distribution
            interaction_type_sql = """
                SELECT interaction_type, COUNT(*) as count
                FROM interactions
                GROUP BY interaction_type
                ORDER BY count DESC
            """
            interaction_types = self.db.select_many(interaction_type_sql)

            # Message type statistics
            message_stats_sql = """
                SELECT 
                    COUNT(*) FILTER (WHERE num_media > 0) as messages_with_media,
                    COUNT(*) FILTER (WHERE num_media = 0) as messages_text_only
                FROM raw_messages
            """
            message_stats = self.db.select_one(message_stats_sql)

            return {
                "total_interactions": interaction_counts['total_interactions'] if interaction_counts else 0,
                "interactions_today": interaction_counts['interactions_today'] if interaction_counts else 0,
                "interactions_this_week": interaction_counts['interactions_this_week'] if interaction_counts else 0,
                "interaction_type_distribution": {row['interaction_type']: row['count'] for row in interaction_types} if interaction_types else {},
                "messages_with_media": message_stats['messages_with_media'] if message_stats else 0,
                "messages_text_only": message_stats['messages_text_only'] if message_stats else 0
            }
        except Exception as e:
            logger.error(f"Error in _get_interaction_analytics: {e}")
            raise

    def get_media_files_by_mem0_id(self, mem0_id_list: List[str]) -> List[Dict[str, Any]]:
        try:
            select_sql = """
                SELECT distinct mf.s3_url
                FROM media_files mf
                INNER JOIN message_media mm ON mf.id = mm.media_file_id
                INNER JOIN memories m ON mm.raw_message_id = m.raw_message_id
                WHERE m.mem0_id IN %s
            """
            result = self.db.select_many(select_sql, (tuple(mem0_id_list) + ("-1",),))
            return result if result else []
        except Exception as e:
            logger.error(f"Error in get_media_files_by_mem0_id for mem0_id {mem0_id_list}: {e}")
            raise
    
# Global database instance
db_service = DatabaseService()
