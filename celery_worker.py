#!/usr/bin/env python3

import os
import sys
import logging
import signal
from typing import List

# Add the project root to Python path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from celery_app import celery_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def signal_handler(signum, frame):
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    sys.exit(0)

def main():
    logger.info("Starting Celery WhatsApp webhook worker...")
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Configure worker options
        worker_options = [
            'worker',
            '--loglevel=info',
            '--queues=webhook_messages',
            '--concurrency=1',  # Process one task at a time
            '--max-tasks-per-child=1000',  # Restart worker after 1000 tasks
            '--without-gossip',  # Disable gossip for better performance
            '--without-mingle',  # Disable mingle for faster startup
            '--without-heartbeat',  # Disable heartbeat if not needed
        ]
        
        
        # Start the worker
        celery_app.start(worker_options)
        
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker error: {str(e)}")
        import traceback
        logger.error(f"Worker traceback: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == '__main__':
    main()
