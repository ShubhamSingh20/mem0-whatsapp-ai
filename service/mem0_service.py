import traceback
from typing import List, Dict, Any, Optional
from mem0 import MemoryClient
from models import MessageWithMedia
from configs import MEM0_API_KEY
import os
from datetime import datetime, timezone


class Mem0Service:

    def __init__(self):
        self.memory = MemoryClient(api_key=MEM0_API_KEY)

    def add_memory(
        self,
        message: MessageWithMedia,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[str]]:
        try:
            # Use user_id from the message if not provided
            if user_id is None:
                user_id = str(message.user.id)
            
            # Build the memory content from the message
            memory_content = self._build_memory_content(message)

            print("memory_content", memory_content)
            
            # Build metadata with required fields
            memory_metadata = self._build_memory_metadata(message, metadata)
            
            # Add memory to mem0
            result = self.memory.add(
                messages=memory_content, 
                user_id=user_id, 
                metadata=memory_metadata,
            )
            

            print(result)
            # Extract mem0 ID from result
            if isinstance(result, dict) and 'results' in result and len(result['results']) > 0:
                return [{"id": i['id'], "memory": i['memory']} for i in result['results']]

            return []
        except Exception as e:
            print(traceback.format_exc())
            return None
    
    def _build_memory_content(self, message: MessageWithMedia) -> List[Dict[str, Any]]:
        content_parts = []
        
        # Add text message if present
        if message.message.body:
            content_parts.append(f"Message: {message.message.body}")
        
        # Add media file information
        if message.media_files:
            content_parts.append(f"Media files: {len(message.media_files)} file(s)")
            for idx, media_file in enumerate(message.media_files):
                media_info = f"Media {idx + 1}: {media_file.content_type}"
                if media_file.description:
                    media_info += f" - {media_file.description}"
                content_parts.append(media_info)
        
        return [{"role": "user", "content": " | ".join(content_parts)}]
    
    def _build_memory_metadata(self, message: MessageWithMedia, additional_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Create timestamp in UTC
        current_utc = datetime.now(timezone.utc)
        
        metadata = {
            "user_id": message.user.id,
            "message_id": message.message.id,
            "timestamp": current_utc.isoformat(),
            "message_type": message.message.message_type,
            "has_media": len(message.media_files) > 0,
            "num_media": len(message.media_files)
        }
        
        # Add media file metadata if present
        if message.media_files:
            media_metadata = []
            for media_file in message.media_files:
                media_info = {
                    "media_id": media_file.id,
                    "content_type": media_file.content_type,
                    "file_size": media_file.file_size,
                    "s3_key": media_file.s3_key
                }
                if media_file.description:
                    media_info["description"] = media_file.description
                media_metadata.append(media_info)
            metadata["media_files"] = media_metadata
        
        # Add user information
        metadata["user_whatsapp_id"] = message.user.whatsapp_id
        metadata["user_phone_number"] = message.user.phone_number
        if message.user.profile_name:
            metadata["user_profile_name"] = message.user.profile_name
        if message.user.timezone:
            metadata["user_timezone"] = message.user.timezone
        
        # Merge with additional metadata if provided
        if additional_metadata:
            metadata.update(additional_metadata)
        
        return metadata

    def get_all_memories(self, user_id: str) -> List[Dict[str, Any]]:
        return self.memory.get_all(user_id=user_id)
    
    def search_memories(self, user_id: str, query: str, filters: Dict | None = None) -> List[Dict[str, Any]]:
        return self.memory.search(user_id=user_id, query=query, filters=filters)
    
    def add_memory_direct(self, user_id: str, memory_text: str, memory_type: str = "user_info", metadata: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        try:
            # Build memory content
            memory_content = [
                {"role": "user", "content": memory_text},
            ]
            
            # Build metadata
            memory_metadata = {
                "memory_type": memory_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "api_direct"
            }
            
            # Add additional metadata if provided
            if metadata:
                memory_metadata.update(metadata)
            
            # Add memory to mem0
            result = self.memory.add(
                messages=memory_content,
                user_id=user_id,
                metadata=memory_metadata,
                version="v2",
                output_format="v1.1",
            )
            
            # Extract mem0 ID from result
            if isinstance(result, dict) and 'results' in result and len(result['results']) > 0:
                return [{"id": i['id'], "memory": i['memory']} for i in result['results']]
            
            return []
        except Exception as e:
            print(f"Error adding memory directly: {e}")
            print(traceback.format_exc())
            return []