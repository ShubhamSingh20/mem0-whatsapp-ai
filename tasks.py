#!/usr/bin/env python3

import os
import sys
import logging
import gc
from typing import Dict, Any
from service.twilio_service import TwilioMediaHelper

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from celery_app import celery_app
from service.assistant_layer import AssistantLayer

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_whatsapp_webhook(self, webhook_data: Dict[str, Any]) -> str:
    message_sid = webhook_data.get('MessageSid', 'Unknown')
    
    try:
        logger.info(f"Starting to process webhook message: {message_sid}")
        
        try:
            assistant_layer = AssistantLayer()
            twilio_media_helper = TwilioMediaHelper()
            
            response = assistant_layer.process_whatsapp_message(webhook_data)

            print("\n\n: RESPONSE", response, "\n\n")

            # twilio_media_helper.send_message(webhook_data.get('From'), response)

        except Exception as process_error:
            logger.error(f"Failed in assistant_layer.process_whatsapp_message: {str(process_error)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise
        
        # Force garbage collection to help with memory management
        gc.collect()
        
        return response
        
    except Exception as e:
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        # Force garbage collection on error too
        gc.collect()
        
        # Retry the task if we haven't exceeded max retries
        if self.request.retries < self.max_retries:
            logger.warning(f"Retrying task {self.request.id} (attempt {self.request.retries + 1}/{self.max_retries})")
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        
        # If we've exhausted retries, raise the exception
        logger.error(f"Task {self.request.id} failed after {self.max_retries} retries")
        raise

