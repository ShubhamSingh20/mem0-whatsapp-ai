from google import genai
from google.genai import types
import os
import pytz
from typing import Optional, Dict, Any, List
import logging
from service.mem0_service import Mem0Service
from datetime import datetime, timezone, timedelta

get_memory_function = types.FunctionDeclaration(
    name="get_memory",
    description="""Retrieve relevant memories and knowledge to help answer the user's query. Use this when you need context or information that might have been shared previously. Also if the query contains terms like i.e "in last one week", "coming weeks", "today" Infer the start_date and end_date based on that provided the current_date in UTC. If no such terms are present let them be null""",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "search_query": types.Schema(
                type=types.Type.STRING,
                description="The search query to find relevant memories. Be specific about what information you're looking for."
            ),
            "start_date": types.Schema(
                type=types.Type.STRING,
                nullable=True,
                description="The start date to find relevant memories, in YYYY-MM-DD format."
            ),
            "end_date": types.Schema(
                type=types.Type.STRING,
                nullable=True,
                description="The end date to find relevant memories, in YYYY-MM-DD format."
            )
        },
        required=["search_query"]
    )
)

store_memory_function = types.FunctionDeclaration(
    name="store_memory",
    description="Store new information as a memory when the user shares likes/dislikes, something useful, makes a decision, completes a task, introduces new entities, or provides feedback/clarification. Summarize the memory in a concise format.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "memory_content": types.Schema(
                type=types.Type.STRING,
                description="The information to store as memory. Include relevant context and details. Summarize the memory in a concise format."
            ),
            "memory_type": types.Schema(
                type=types.Type.STRING,
                description="Type of memory being stored",
                enum=["preference", "decision", "task_completion", "entity", "feedback", "general_info"]
            )
        },
        required=["memory_content", "memory_type"]
    )
)


class GeminiService:
    """A simple reusable class for analyzing videos using Google's Gemini API."""
    
    def __init__(
        self,
        location: str = "global",
        model: str = "gemini-2.5-flash",
        memory_service: Optional[Mem0Service] = None
    ):
        """
        Initialize the Gemini Video Analyzer.
        
        Args:
            project_id: Google Cloud project ID
            location: Location for the Vertex AI service
            credentials_path: Path to service account credentials JSON file
            model: Gemini model to use
        """
        self.location = location
        self.model = model
        self.memory_service = memory_service
        
        # Initialize the client
        try:
            self.client = genai.Client(vertexai=True,location=self.location)
        except Exception as e:
            logging.error(f"Failed to initialize Gemini client: {e}")
            raise
    
    def analyze_media(
        self,
        url: str,
        mime_type: str = "video/mp4",
        temperature: float = 0,
        max_output_tokens: int = 65535,
        stream: bool = True
    ) -> str:
        # Validate inputs
        if not url or not url.strip():
            raise ValueError("url cannot be empty")
        if not (0 <= temperature <= 1):
            raise ValueError("temperature must be between 0 and 1")
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        # Create media part
        media_part = types.Part.from_uri(
            file_uri=url,
            mime_type=mime_type,
        )

        is_image = any(mime_type.startswith(prefix) for prefix in ["image/", "photo/"])

        if is_image:
            prompt = """
For the given image, describe the image in concise and too the point. Do not include any other text.
"""
        else:
            prompt = """
For the given video, transcribe the video/audio and transcribe to text in simple paragraphs with without any timestamps and no speaker diarization .
"""

        # Create text part
        text_part = types.Part.from_text(text=prompt)
        
        # Create content
        contents = [
            types.Content(role="user", parts=[media_part, text_part]),
        ]
        
        # Configure generation
        config = types.GenerateContentConfig(
            temperature=temperature,
            top_p=0.95,
            seed=0,
            max_output_tokens=max_output_tokens,
            safety_settings=[
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
            ],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        
        try:
            if stream:
                result = ""
                for chunk in self.client.models.generate_content_stream(
                    model=self.model,
                    contents=contents,
                    config=config,
                ):
                    if chunk.text:
                        result += chunk.text
                #         print(chunk.text, end="")
                # print()  # Add newline at the end
                return result
            else:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
                return response.text
        except Exception as e:
            logging.error(f"Failed to generate content: {e}")
            raise

    def _format_memories_as_context(self, memories: List[Dict[str, Any]]) -> str:
        if not memories:
            return ""
        
        context_parts = ["=== RETRIEVED MEMORIES (for context) ==="]
        
        for i, memory in enumerate(memories, 1):
            memory_text = memory.get('memory', memory.get('text', ''))
            if memory_text:
                context_parts.append(f"{i}. {memory_text}")
        
        context_parts.append("=== END OF MEMORIES ===\n")
        
        return "\n".join(context_parts)

    def prompt_run(self, prompt: str) -> str:
        return self.client.models.generate_content(
            model=self.model,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(
                temperature=0,
                top_p=0.95,
                seed=0,
                max_output_tokens=65535,
            ),
        )

    def llm_conversation(
        self, 
        query: str, 
        user_id: str,
        conversation_history: str = "",
        temperature: float = 0,
        attached_media_files: List[str] = [],
        max_output_tokens: int = 4096,
        **kwargs
    ) -> Dict[str, Any]:

        # Define memory tool for function calling
        memory_tool = types.Tool(
            function_declarations=[get_memory_function, store_memory_function]
        )

        # Initial system/user prompt
        system_prompt = f"""
CURRENT_DATE: {datetime.now(timezone.utc).strftime("%Y-%m-%d")}
You are a helpful AI assistant named Whatsy! with access to memory functions. Your role is to:

1. Answer user queries accurately and helpfully
2. Use get_memory to retrieve relevant context when needed or when user ask for something specific which you are not aware of it and want to do a lookup in knowledge base.
3. You have been provided with the conversation history of the user, to help better answer follow up questions.
4. Use store_memory to save important information from users chat:
    This includes:
    * Preferences: likes, dislikes, favorites (e.g., “I prefer Italian food”).
    * Decisions: commitments, choices, or resolutions (e.g., “I’ll go with the cheaper plan”).
    * Tasks & Plans: to-dos, reminders, schedules, or events (e.g., “I need to call mom tomorrow”).
    * Facts about their life: updates, achievements, health changes, routines (e.g., “I started a new job”).
    * Feedback: opinions about the assistant or the experience (e.g., “Please answer more briefly next time”).
    * Entities: names of people, places, pets, organizations, or other recurring references.
    * Do not store trivial acknowledgements (e.g., “hi”, “ok”, “thanks”) or ephemeral chit-chat that has no future value.


When you retrieve memories, use them to provide more informed responses.
Always be conversational and helpful and at the same time be concise and to the point, do not be verbose.

{f"Conversation history: \n\n{conversation_history}" if conversation_history else ""}
"""
        user_prompt = f"""
User : {query}
"""

        if attached_media_files:
            user_prompt += f"\nUser Attached Following Media Files: \n\n{attached_media_files}"

        contents = [
            types.Content(
                role="user", 
                parts=[types.Part.from_text(text=system_prompt + user_prompt)]
            )
        ]

        config = types.GenerateContentConfig(
            temperature=temperature,
            top_p=0.95,
            max_output_tokens=max_output_tokens,
            tools=[memory_tool],
            safety_settings=[
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
            ]
        )

        # Final structured result
        result = {
            "response": "",
            "function_calls": [],
            "memories_retrieved": [],
            "memories_stored": []
        }

        try:
            # === Step 1: Get initial response (may contain function calls) ===
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config
            )

            function_calls, function_responses = self._process_function_calls(
                response, user_id, result, **kwargs
            )

            if function_calls:
                contents.extend([response.candidates[0].content])  # Add model's call
                contents.append(types.Content(role="function", parts=function_responses))

                # Add memory context if any were retrieved
                if result["memories_retrieved"]:
                    memory_context = self._format_memories_as_context(result["memories_retrieved"])
                    contents.append(
                        types.Content(
                            role="user",
                            parts=[types.Part.from_text(
                                text=f"""{memory_context}
Please use these memories as context to answer the original query:
{query}
"""
                            )]
                        )
                    )

                # Generate final response
                final_response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        top_p=0.95,
                        max_output_tokens=max_output_tokens,
                        safety_settings=config.safety_settings
                    )
                )
                result["response"] = final_response.text or ""
            else:
                # No function calls — use direct response
                result["response"] = response.text or ""

        except Exception as e:
            logging.error(f"Failed to process llm_conversation: {e}")
            result["response"] = f"⚠️ Error while processing your request: {str(e)}"

        return result


    def _process_function_calls(self, response, user_id: str, result: Dict[str, Any], **kwargs):
        function_calls, function_responses = [], []

        if not (response.candidates and response.candidates[0].content.parts):
            return function_calls, function_responses

        for part in response.candidates[0].content.parts:
            if not (hasattr(part, "function_call") and part.function_call):
                continue

            fc = part.function_call
            function_calls.append(fc)
            result["function_calls"].append({
                "name": fc.name,
                "args": dict(fc.args) if fc.args else {}
            })

            if fc.name == "get_memory" and self.memory_service:
                mem0_filters = kwargs.get('mem0_filters', {})
                user_timezone = kwargs.get("user_timezone", "UTC")
                start_date = fc.args.get("start_date", None)
                end_date = fc.args.get("end_date", None)

                if start_date and end_date:
                    # parse input dates as naive datetime
                    start_date = datetime.strptime(start_date, "%Y-%m-%d")
                    end_date = datetime.strptime(end_date, "%Y-%m-%d")

                    # localize to user tz
                    tz = pytz.timezone(user_timezone or "Asia/Calcutta")
                    start_date = tz.localize(start_date)
                    end_date = tz.localize(end_date) + timedelta(days=1)  # make end exclusive

                    # convert back to UTC for querying
                    start_date = start_date.astimezone(pytz.UTC)
                    end_date = end_date.astimezone(pytz.UTC)

                    mem0_filters = {
                        "AND": [
                            {
                                "created_at": {
                                    "gte": start_date.strftime("%Y-%m-%d"),
                                    "lte": end_date.strftime("%Y-%m-%d")
                                }
                            }
                        ],
                        'user_id': user_id,
                        **mem0_filters
                    }

                memories = self.memory_service.search_memories(
                    user_id=user_id,
                    query=fc.args.get("search_query", ""),
                    filters=mem0_filters
                )

                result["memories_retrieved"].extend(memories)

                function_responses.append(
                    types.Part.from_function_response(
                        name="get_memory",
                        response={"memories": memories}
                    )
                )

            elif fc.name == "store_memory" and self.memory_service:
                memory_content = fc.args.get("memory_content", "")
                memory_type = fc.args.get("memory_type", "general_info")

                try:
                    stored = self.memory_service.memory.add(
                        messages=[{"role": "user", "content": memory_content}],
                        user_id=user_id,
                        metadata={"type": memory_type, "source": "llm_conversation"}
                    )
                    result["memories_stored"].append(stored)

                    function_responses.append(
                        types.Part.from_function_response(
                            name="store_memory",
                            response={"status": "stored", "content": memory_content}
                        )
                    )

                    logging.info(f"Successfully stored memory: {memory_content}")
                except Exception as e:
                    logging.error(f"Failed to store memory: {e}")
                    function_responses.append(
                        types.Part.from_function_response(
                            name="store_memory",
                            response={"status": "error", "message": str(e)}
                        )
                    )

        return function_calls, function_responses
