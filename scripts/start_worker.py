#!/usr/bin/env python3

import os
import sys
import subprocess
import signal
import time
import logging

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def start_worker():
    """Start the Celery worker process."""
    worker_script = os.path.join(project_root, 'celery_worker.py')
    
    if not os.path.exists(worker_script):
        logger.error(f"Celery worker script not found: {worker_script}")
        return False
    
    try:
        logger.info("Starting Celery worker...")
        logger.info("Press Ctrl+C to stop the worker")
        
        # Start the worker as a subprocess
        process = subprocess.Popen([
            sys.executable, worker_script
        ], cwd=project_root)
        
        # Wait for the process to complete
        process.wait()
        
        return True
        
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
        if process:
            process.terminate()
            process.wait()
        return True
    except Exception as e:
        logger.error(f"Error starting worker: {str(e)}")
        if process:
            process.terminate()
            process.wait()
        return False

def main():
    """Main function."""
    logger.info("WhatsApp Celery Worker Startup Script")
    logger.info("=" * 40)
    # Start the worker
    if not start_worker():
        sys.exit(1)

if __name__ == '__main__':
    main()
