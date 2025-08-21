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

    def get_all_memories(self, user_id: str) -> List[Dict[str, Any]]:
        return self.memory.get_all(user_id=user_id)
    
    def search_memories(self, user_id: str, query: str, filters: Dict | None = None) -> List[Dict[str, Any]]:
        return self.memory.search(user_id=user_id, query=query, filters=filters)
    
    def add_memory(self, user_id: str, memory_text: str, memory_type: str = "user_info", metadata: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        try:
            # Build memory content
            memory_content = [
                {"role": "user", "content": memory_text},
                {"role": "assistant", "content": "Ok thanks will keep it in mind"}
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

            return result.get('results', [])
        except Exception as e:
            traceback.print_exc()
            print(f"Error adding memory directly: {e}")
            return []