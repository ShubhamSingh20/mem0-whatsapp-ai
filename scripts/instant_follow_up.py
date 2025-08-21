#!/usr/bin/env python3

# python3 -m scripts.instant_follow_up
from service import *

def main():
    user_id = "apple_5"

    # Initialize services
    mem0_service = Mem0Service()
    mem0_service.add_memory(user_id, "I love Italian food, especially red sauce asta")
    
    gemini_service = GeminiService(memory_service=mem0_service)
    
    # Example user ID
    
    print("=== LLM Conversation with Memory Function Calling ===\n")
    
    # Example 1: User shares a preference (should trigger store_memory)
    query1 = "what else pairs with those ?"
    result1 = gemini_service.llm_conversation(
        query=query1,
        user_id=user_id
    )
    
    print(f"Query: {query1}")
    print(f"Response: {result1['response']}")
    print(f"Function calls made: {result1['function_calls']}")
    print(f"Memories stored: {len(result1['memories_stored'])}")
    print("-" * 50)
    

if __name__ == "__main__":
    main()
