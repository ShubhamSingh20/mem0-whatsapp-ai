#!/usr/bin/env python3

from service.gemini_service import GeminiService
from service.mem0_service import Mem0Service


def main():
    """Demonstrate the llm_conversation function with memory operations."""
    
    # Initialize services
    mem0_service = Mem0Service()
    gemini_service = GeminiService(memory_service=mem0_service)
    
    # Example user ID
    user_id = "1"
    
    print("=== LLM Conversation with Memory Function Calling ===\n")
    
    # Example 1: User shares a preference (should trigger store_memory)
    print("Example 1: User shares a preference")
    query1 = "what all memories were created last month?"
    result1 = gemini_service.llm_conversation(
        query=query1,
        user_id=user_id
    )
    
    print(f"Query: {query1}")
    print(f"Response: {result1['response']}")
    print(f"Function calls made: {result1['function_calls']}")
    print(f"Memories stored: {len(result1['memories_stored'])}")
    print("-" * 50)
    
    
    # # Example 3: User completes a task (should trigger store_memory)
    # print("\nExample 3: User completes a task")
    # query3 = "I just finished my workout session today. Did 30 minutes of cardio and felt great!"
    # result3 = gemini_service.llm_conversation(
    #     query=query3,
    #     user_id=user_id,
    #     mem0_service=mem0_service
    # )
    
    # print(f"Query: {query3}")
    # print(f"Response: {result3['response']}")
    # print(f"Function calls made: {result3['function_calls']}")
    # print(f"Memories stored: {len(result3['memories_stored'])}")
    # print("-" * 50)
    
    # # Example 4: General question (may or may not trigger function calls)
    # print("\nExample 4: General question")
    # query4 = "What's the best way to stay motivated for exercise?"
    # result4 = gemini_service.llm_conversation(
    #     query=query4,
    #     user_id=user_id,
    #     mem0_service=mem0_service
    # )
    
    # print(f"Query: {query4}")
    # print(f"Response: {result4['response']}")
    # print(f"Function calls made: {result4['function_calls']}")
    # print(f"Memories retrieved: {len(result4['memories_retrieved'])}")
    # print("-" * 50)
    
    # # Example 5: User introduces a new entity (should trigger store_memory)
    # print("\nExample 5: User introduces a new entity")
    # query5 = "I joined a new gym called FitZone downtown. They have great equipment and friendly staff."
    # result5 = gemini_service.llm_conversation(
    #     query=query5,
    #     user_id=user_id,
    #     mem0_service=mem0_service
    # )
    
    # print(f"Query: {query5}")
    # print(f"Response: {result5['response']}")
    # print(f"Function calls made: {result5['function_calls']}")
    # print(f"Memories stored: {len(result5['memories_stored'])}")
    
    # print("\n=== End of Examples ===")


if __name__ == "__main__":
    main()
