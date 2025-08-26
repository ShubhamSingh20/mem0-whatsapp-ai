import logging
from typing import List, Optional
import traceback
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response, Query
from pydantic import BaseModel, Field
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime
from models import CreateMemoryRequest, GetMemoryRequest, ListMemoriesRequest, WhatsappWebhook, AnalyticsResponse
from service.assistant_layer import AssistantLayer
from service.database import db_service
from service.mem0_service import Mem0Service
from service.celery_service import celery_service
from utils import infer_timezone_from_number

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="Whatsapp AI",
    description="Whatsapp AI - Simple chatbot",
    version="1.0.0"
)

assistant_layer = AssistantLayer()
mem0_service = Mem0Service()

def handle_list_command(webhook_data: WhatsappWebhook) -> str:
    user_record = db_service.get_user_by_whatsapp_number(
        webhook_data.from_.replace("whatsapp:", "")
    )

    if not user_record:
        return "No user found"
    
    memories = db_service.list_memories(user_record['id'])

    memories_str = ""

    for memory in memories:
        memories_str += f"ID: {memory['id']} Mem0 ID: {memory['mem0_id']}\n"
        memories_str += f"Info: {memory['mem0_infered_memory']}\n\n"
        memories_str += f"--------------------------------\n"

    sourced_memories = db_service.get_sourced_memories(user_record['id'])

    if sourced_memories:
        memories_str += "\nSourced Memories (API):\n"
        for memory in sourced_memories:
            memories_str += f"ID: {memory['id']} Mem0 ID: {memory['mem0_id']}\n"
            memories_str += f"Info: {memory['mem0_infered_memory']}\n\n"
            memories_str += f"--------------------------------\n"

    return memories_str


@app.post("/webhook")
async def webhook(request: Request):
    try:
        form = await request.form()
        data = dict(form)

        # logger.info(f"Incoming WhatsApp webhook data: {data}")

        # Extract media information
        num_media = int(data.get("NumMedia", 0))
        media_urls = []
        media_types = []

        for i in range(num_media):
            media_url = data.get(f"MediaUrl{i}", "")
            media_type = data.get(f"MediaContentType{i}", "")
            if media_url:
                media_urls.append(media_url)
                media_types.append(media_type)

        # Create webhook data model for validation
        webhook_data = WhatsappWebhook(
            **data,
            media_urls=media_urls,
            media_content_types=media_types,
            timezone=infer_timezone_from_number(data.get("From", ""))
        )

        if webhook_data.body.strip().startswith("/list"):
            twiml = MessagingResponse()
            output = handle_list_command(webhook_data)
            twiml.message(output)
            print(twiml)
            return Response(content=str(twiml), media_type="application/xml")


        # Try to enqueue the message for asynchronous processing

        if celery_service.is_redis_available():
            quick_twiml = MessagingResponse()
            task_id = celery_service.enqueue_webhook_message(data)
            
            # Send acknowledgment response
            return Response(content=str(quick_twiml), media_type="application/xml")

        # Fallback to synchronous processing if Redis is unavailable
        logger.warning("Redis unavailable, falling back to synchronous processing")
        response = assistant_layer.process_whatsapp_message(data)
        twiml_response = MessagingResponse()
        twiml_response.message(response)
        print(twiml_response)
        return Response(content=str(twiml_response), media_type="application/xml")
    
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Webhook error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Webhook processing failed: {str(e)}")

@app.post("/memories")
async def create_memory(memory_request: CreateMemoryRequest):
    """
    Create a memory for a user identified by whatsapp_number or user_id.
    """
    try:
        # Validate that either whatsapp_number or user_id is provided
        if not memory_request.whatsapp_number:
            raise HTTPException(
                status_code=400, 
                detail="whatsapp_number is required"
            )
        
        # Validate memory_text is provided
        if not memory_request.memory_text or not memory_request.memory_text.strip():
            raise HTTPException(
                status_code=400,
                detail="memory_text is required and cannot be empty"
            )
        
        # Determine user_id
        user_id = db_service.get_user_by_whatsapp_number(memory_request.whatsapp_number)

        if not user_id:
            raise HTTPException(
                status_code=404,
                detail=f"User not found with WhatsApp number: {memory_request.whatsapp_number}"
            )
        
        user_id = user_id['id']
    
        memory_id = assistant_layer.store_memory(user_id, memory_request.memory_text.strip(), memory_request.memory_type, memory_request.metadata)

        return {
            "message": "Memory created successfully",
            "user_id": user_id,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error creating memory: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to create memory: {str(e)}"
        )

@app.get("/memories")
async def get_memories(
    whatsapp_number: Optional[str] = Query(None, description="WhatsApp number with country code", example="+14155552345"),
    query: Optional[str] = Query(None, description="Search query to filter memories", example="food preferences"),
):
    """
    Get memories for a user identified by whatsapp_number or user_id.
    Optionally search memories with a query string.
    """
    try:
        # Validate that either whatsapp_number or user_id is provided
        if not whatsapp_number:
            raise HTTPException(
                status_code=400, 
                detail="whatsapp_number is required"
            )
        
        # Determine user_id
        user_record = db_service.get_user_by_whatsapp_number(whatsapp_number)

        if not user_record:
            raise HTTPException(
                status_code=404,
                detail=f"User not found with WhatsApp number: {whatsapp_number}"
            )
        target_user_id = user_record['id']
        
        
        if not user_record:
            raise HTTPException(
                status_code=404,
                detail=f"User not found with whatsapp number: {whatsapp_number}"
            )
        
        try:
            search_results = assistant_layer.search_for_memories(str(target_user_id), query)
            
            return {
                "success": True,
                "user_id": target_user_id,
                "user_info": {
                    "whatsapp_id": user_record['whatsapp_id'] if user_record else None,
                    "phone_number": user_record['phone_number'] if user_record else None,
                    "profile_name": user_record['profile_name'] if user_record else None
                },
                "query": query,
                "results_count": len(search_results),
                "search_results": search_results
            }
            
        except Exception as search_error:
            logger.error(f"Failed to search memories: {search_error}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to search memories: {str(search_error)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting memories: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to get memories: {str(e)}"
        )

@app.post("/memories/list")
async def list_memories(request: ListMemoriesRequest):
    """
    List all memories for a user based on their WhatsApp number.
    Returns memories from the local database only, ordered by newest first.
    """
    try:
        # Validate whatsapp_number is provided
        if not request.whatsapp_number:
            raise HTTPException(
                status_code=400,
                detail="whatsapp_number is required"
            )
        
        user_record = db_service.get_user_by_whatsapp_number(request.whatsapp_number)
        
        if not user_record:
            raise HTTPException(
                status_code=404,
                detail=f"User not found with WhatsApp number: {request.whatsapp_number}"
            )
        
        memories = assistant_layer.get_memories_by_user_id(user_record)

        return memories
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing memories: {str(e)}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list memories: {str(e)}"
        )

@app.get("/interactions/recent")
async def get_recent_interactions(
    whatsapp_number: str = Query(..., description="WhatsApp number with country code", example="+14155552345"),
    limit: int = Query(10, description="Maximum number of interactions to return", example=10)
):
    if not whatsapp_number:
        raise HTTPException(
            status_code=400,
            detail="whatsapp_number is required"
        )
    user = db_service.get_user_by_whatsapp_number(whatsapp_number)

    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User not found with WhatsApp number: {whatsapp_number}"
        )
    
    user_id = user['id']
    
    try:
        interactions = assistant_layer.get_recent_interactions(user_id, limit)
        return interactions
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error getting recent interactions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get recent interactions: {str(e)}"
        )

@app.get("/analytics/summary", response_model=AnalyticsResponse)
async def get_analytics_summary():
    try:
        analytics_data = db_service.get_analytics_summary()
        
        # Add generated timestamp
        analytics_data["generated_at"] = datetime.now()
        
        return AnalyticsResponse(**analytics_data)
        
    except Exception as e:
        logger.error(f"Error getting analytics summary: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve analytics summary: {str(e)}"
        )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
