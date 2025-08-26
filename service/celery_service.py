
import os
import logging
from typing import Dict, Any
import redis
from celery import Celery

logger = logging.getLogger(__name__)

class CeleryService:
    
    def __init__(self):
        # Redis configuration
        self.redis_host = os.getenv('REDIS_HOST')
        self.redis_port = int(os.getenv('REDIS_PORT'))
        self.redis_db = int(os.getenv('REDIS_DB'))
        self.redis_password = os.getenv('REDIS_PASSWORD')
        
        self._redis_conn = None
        self._celery_app = None
        
    def _get_redis_connection(self):
        """Get or create Redis connection."""
        if self._redis_conn is None:
            try:
                self._redis_conn = redis.Redis(
                    host=self.redis_host,
                    port=self.redis_port,
                    db=self.redis_db,
                    password=self.redis_password,
                    decode_responses=False,  # Let Celery handle encoding/decoding
                    encoding='utf-8',
                    encoding_errors='replace'  # Replace invalid characters instead of failing
                )
                # Test the connection
                self._redis_conn.ping()
            except redis.ConnectionError as e:
                logger.error(f"Failed to connect to Redis: {str(e)}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error connecting to Redis: {str(e)}")
                raise
        
        return self._redis_conn
    
    def _get_celery_app(self):
        """Get or create Celery app instance."""
        if self._celery_app is None:
            from celery_app import celery_app
            self._celery_app = celery_app
        
        return self._celery_app
    
    def enqueue_webhook_message(self, webhook_data: Dict[str, Any], task_timeout: int = 300) -> str:
        try:
            celery_app = self._get_celery_app()
            
            # Import the task
            from tasks import process_whatsapp_webhook
            
            # Enqueue the task
            task_result = process_whatsapp_webhook.apply_async(
                args=[webhook_data],
                kwargs={},
                task_id=webhook_data.get('MessageSid'),  # Use MessageSid as task ID for deduplication
                queue='webhook_messages',
                expires=task_timeout,
                soft_time_limit=task_timeout - 30,  # Soft timeout 30s before hard timeout
                time_limit=task_timeout,  # Hard timeout
            )
            
            logger.info(f"Enqueued webhook message with task ID: {task_result.id}")
            return task_result.id
            
        except Exception as e:
            logger.error(f"Failed to enqueue webhook message: {str(e)}")
            raise
    
    def is_redis_available(self) -> bool:
        try:
            redis_conn = self._get_redis_connection()
            redis_conn.ping()
            return True
        except Exception:
            return False

# Global celery service instance
celery_service = CeleryService()
