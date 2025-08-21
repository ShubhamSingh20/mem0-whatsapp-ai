#!/usr/bin/env python3
"""
Celery application configuration for WhatsApp webhook processing.

This module sets up the Celery app with Redis as the broker and includes
task definitions for processing WhatsApp messages asynchronously.
"""

import os
import logging
from celery import Celery
from celery.signals import setup_logging
from configs import REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD

# Configure logging
@setup_logging.connect
def config_loggers(*args, **kwargs):
    from logging.config import dictConfig
    dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'default': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'default',
            },
        },
        'root': {
            'level': 'INFO',
            'handlers': ['console'],
        },
    })

logger = logging.getLogger(__name__)

# Redis connection configuration

# Construct Redis URL
if REDIS_PASSWORD:
    REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
else:
    REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# Create Celery app
celery_app = Celery(
    'whatsapp_processor',
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=['tasks']  # Include task modules
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer='json',
    accept_content=['json'],  # Ignore other content
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Redis settings
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    
    # Worker settings
    worker_prefetch_multiplier=1,  # Process one task at a time
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks to prevent memory leaks
    
    # Task routing
    task_routes={
        'tasks.process_whatsapp_webhook': {'queue': 'webhook_messages'},
    },
    
    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    result_backend_transport_options={
        'socket_keepalive': True,
        'socket_keepalive_options': {
            'TCP_KEEPINTVL': 1,
            'TCP_KEEPCNT': 3,
            'TCP_KEEPIDLE': 1,
        },
    },
    
    # Error handling
    task_reject_on_worker_lost=True,
    task_acks_late=True,  # Acknowledge task after completion
)

if __name__ == '__main__':
    celery_app.start()
