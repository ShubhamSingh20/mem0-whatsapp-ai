from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
import json

class User(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: Optional[int] = None
    whatsapp_id: str = Field(
        ...,
        description="WhatsApp ID (usually same as phone number)",
        example="+14155552345"
    )
    phone_number: str = Field(
        ...,
        description="Phone number with country code",
        example="+14155552345"
    )
    timezone: Optional[str] = Field(
        default=None,
        description="User's timezone",
        example="America/New_York"
    )
    profile_name: Optional[str] = Field(
        default=None,
        description="User's profile name from WhatsApp",
        example="John Doe"
    )
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_active: bool = True

class RawMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: Optional[int] = None
    user_id: int
    message_sid: str
    sms_message_sid: Optional[str] = None
    body: Optional[str] = None
    message_type: str = "text"
    from_number: str
    to_number: str
    status: str = "received"
    num_media: int = 0
    account_sid: Optional[str] = None
    api_version: Optional[str] = None
    created_at: Optional[datetime] = None
    raw_data: Optional[Dict[str, Any]] = None

class MediaFile(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: Optional[int] = None
    raw_message_id: int
    media_sid: Optional[str] = None
    content_type: Optional[str] = None
    file_size: Optional[int] = None
    file_hash: Optional[str] = None
    s3_key: Optional[str] = None
    s3_url: Optional[str] = None
    forwarded_count: int = 0
    description: Optional[str] = None
    created_at: Optional[datetime] = None


class Memory(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: Optional[int] = None
    user_id: int
    text: str
    memory_type: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    embedding: Optional[List[float]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class MemoryMedia(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: Optional[int] = None
    memory_id: int
    media_file_id: int
    created_at: Optional[datetime] = None

class Interaction(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: Optional[int] = None
    user_id: int
    raw_message_id: int
    user_message: str
    bot_response: Optional[str] = None
    interaction_type: str = "conversation"  # conversation, memory_query, system_message
    status: str = "pending"  # pending, processing, completed, failed
    memories_retrieved: Optional[Dict[str, Any]] = None  # Array of memory IDs and content retrieved
    memories_saved: Optional[Dict[str, Any]] = None  # Array of memory IDs created/updated
    memory_operation_type: Optional[str] = None  # retrieve, save, update, delete, none
    processing_time_ms: Optional[int] = None
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    context_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# Request/Response models for API
class CreateUserRequest(BaseModel):
    whatsapp_id: str = Field(
        ...,
        description="WhatsApp ID (usually same as phone number)",
        example="+14155552345"
    )
    phone_number: str = Field(
        ...,
        description="Phone number with country code",
        example="+14155552345"
    )
    profile_name: Optional[str] = Field(
        default=None,
        description="User's profile name from WhatsApp",
        example="John Doe"
    )

class CreateMessageRequest(BaseModel):
    user_id: int
    message_sid: str
    body: Optional[str] = None
    message_type: str = "text"
    from_number: str
    to_number: str
    media_urls: Optional[List[str]] = []
    media_content_types: Optional[List[str]] = []
    raw_data: Optional[Dict[str, Any]] = None

class MessageWithMedia(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    message: RawMessage
    media_files: List[MediaFile] = []
    user: User

class CreateInteractionRequest(BaseModel):
    user_id: int
    raw_message_id: int
    user_message: str
    interaction_type: str = "conversation"
    context_data: Optional[Dict[str, Any]] = None

class UpdateInteractionRequest(BaseModel):
    bot_response: Optional[str] = None
    status: Optional[str] = None
    memories_retrieved: Optional[Dict[str, Any]] = None
    memories_saved: Optional[Dict[str, Any]] = None
    memory_operation_type: Optional[str] = None
    processing_time_ms: Optional[int] = None
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    error_message: Optional[str] = None

class InteractionWithDetails(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    interaction: Interaction
    user: User
    raw_message: RawMessage



class WhatsappWebhook(BaseModel):
    model_config = ConfigDict(populate_by_name=True)   # allows using snake_case internally
    
    sms_message_sid: str = Field(..., alias="SmsMessageSid")
    num_media: int = Field(..., alias="NumMedia")
    sms_sid: str = Field(..., alias="SmsSid")
    sms_status: str = Field(..., alias="SmsStatus")
    body: str = Field(..., alias="Body")
    to: str = Field(..., alias="To")
    from_: str = Field(..., alias="From")   # `from` is reserved in Python
    account_sid: str = Field(..., alias="AccountSid")
    api_version: str = Field(..., alias="ApiVersion")
    media_urls: Optional[List[str]] = None
    media_content_types: Optional[List[str]] = None

class CreateMemoryRequest(BaseModel):
    # Either whatsapp_number OR user_id must be provided
    whatsapp_number: str = Field(
        ..., 
        description="WhatsApp number with country code", 
        example="+14155552345"
    )
    
    memory_text: str = Field(
        ..., 
        description="The memory text to store",
        example="User prefers vegetarian food and likes spicy cuisine"
    )
    memory_type: Optional[str] = Field(
        default="user_info",
        description="Type of memory being stored",
        example="user_info"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional metadata for the memory",
        example={"source": "conversation", "confidence": 0.9}
    )

class GetMemoryRequest(BaseModel):
    # Either whatsapp_number OR user_id must be provided
    whatsapp_number: Optional[str] = Field(
        default=None,
        description="WhatsApp number with country code",
        example="+14155552345"
    )
    user_id: Optional[int] = Field(
        default=None,
        description="User ID from database",
        example=123
    )
    
    # Optional query to search for specific memories
    query: Optional[str] = Field(
        default=None,
        description="Search query to filter memories",
        example="food preferences"
    )
    
    # Optional limit for results
    limit: Optional[int] = Field(
        default=10,
        description="Maximum number of results to return",
        example=10
    )

class ListMemoriesRequest(BaseModel):
    whatsapp_number: str = Field(
        ...,
        description="WhatsApp number with country code",
        example="+14155552345"
    )
