from service.mem0_service import Mem0Service
from service.twilio_service import TwilioMediaHelper
from service.gemini_service import GeminiService
from utils import infer_timezone_from_number
from service.object_storage import ObjectStorageService
from service.database import db_service
from models import WhatsappWebhook, User, RawMessage, MessageWithMedia, MediaFile
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import os
import uuid

logger = logging.getLogger(__name__)

class AssistantLayer:
    def __init__(self):
        self.file_service = ObjectStorageService()
        self.memory_service = Mem0Service()
        self.twilio_service = TwilioMediaHelper()
        self.db = db_service
        self.gemini_service = GeminiService(memory_service=self.memory_service)
    
    def process_whatsapp_message(self, data: WhatsappWebhook) -> str:
        try:
            message_sid = data.get('MessageSid', '')
            
            # Extract user information from webhook data
            whatsapp_id = data.get('WaId', '')
            phone_number = data.get('From', '').replace('whatsapp:', '')
            profile_name = data.get('ProfileName')
            timezone = infer_timezone_from_number(phone_number)
            
            # Get or create user
            user = self.db.get_or_create_user(
                whatsapp_id=whatsapp_id,
                phone_number=phone_number,
                profile_name=profile_name,
                timezone=timezone
            )
            
            # Check if this message has already been processed (idempotency check)
            existing_message = self.db.get_raw_message_by_sid(message_sid)
            is_duplicate = existing_message is not None
            
            if is_duplicate:
                logger.info(f"Processing duplicate message with SID: {message_sid}. Using existing data.")
                interaction = self.db.get_interaction_by_message_id(existing_message.id)
                if interaction:
                    return interaction['bot_response']
            else:
                # Store new raw message (idempotent method will handle duplicates)
                message_text = data.get('Body')

                if not message_text and int(data.get('NumMedia', 0)) > 0:
                    message_text = "User only sent a media attachment"

                raw_message = self.db.store_raw_message(
                    user_id=user.id,
                    message_sid=message_sid,
                    body=message_text,
                    message_type=data.get('MessageType', 'text'),
                    from_number=data.get('From', ''),
                    to_number=data.get('To', ''),
                    status='received',
                    num_media=int(data.get('NumMedia', 0)),
                    account_sid=data.get('AccountSid'),
                    api_version=data.get('ApiVersion'),
                    sms_message_sid=data.get('SmsMessageSid'),
                    raw_data=data
                )
                
                # Process media files if any (only for new messages)
                media_files = []
                if int(data.get('NumMedia', 0)) > 0:
                    media_files = self.process_media_files(raw_message.id, data)

            message_with_media = MessageWithMedia(
                message=raw_message,
                media_files=media_files,
                user=user
            )

            past_interactions = self.get_formatted_past_interactions(user.id)
            
            if is_duplicate:
                # return bot response from the interaction table
                interaction = self.db.get_interactions_by_user_id(user.id, 1, detailed=True)[0]
                return interaction['bot_response']

            text_only_message = raw_message.body or "User only sent a media attachment"

            attached_media_files = []
            for media_file in message_with_media.media_files:
                formatted_string = (
                    "MEDIA FILE: {media_file.media_sid} {media_file.content_type}\n"
                    "DESCRIPTION: {media_file.description}"
                ).format(media_file=media_file)

                attached_media_files.append(formatted_string)

            response_obj = self.gemini_service.llm_conversation(
                text_only_message, user.id, user_timezone=user.timezone or "UTC", 
                conversation_history=past_interactions, attached_media_files=attached_media_files
            )
            chat_response = response_obj['response']
            print(response_obj)
            
            # [{'results': [{'id': '8e5bf579-99f4-4331-a935-3874000a915f', 'event': 'UPDATE', 'memory': 'Shubham Singh is approximately 25 years old', 'previous_memory': 'Shubham Singh is about 25 years old'}, {'id': '5fdddae6-f30b-4734-8496-43f9cd7542db', 'event': 'ADD', 'memory': "User's product is a SAAS company for user behavior analytics", 'structured_attributes': {'day': 20, 'hour': 13, 'year': 2025, 'month': 8, 'minute': 9, 'quarter': 3, 'is_weekend': False, 'day_of_week': 'wednesday', 'day_of_year': 232, 'week_of_year': 34}}]}]
            # store the memory_content in the database
            for mem in response_obj['memories_stored']:
                for mem0_id in mem['results']:
                    if mem0_id['event'] == 'ADD':
                        self.db.store_memory(user.id, raw_message.id, mem0_id['id'], mem0_id['memory'])
                    elif mem0_id['event'] == 'UPDATE':
                        self.db.update_memory(raw_message.id, mem0_id['id'], mem0_id['memory'])
                    elif mem0_id['event'] == 'DELETE':
                        self.db.delete_memory(mem0_id['id'])

            sources = []
            for mem in response_obj['memories_retrieved']:
                sources.append(mem['id'])

            # # Storing interaction
            self.db.store_interaction(user.id, raw_message.id, text_only_message, chat_response, "conversation", sources)

            return chat_response

        except Exception as e:
            logger.error(f"Error processing WhatsApp message: {e}")
            raise

    def search_for_memories(self, user_id: int, query: str) -> List[Dict[str, Any]]:
        """
        Search for memories for a user.
        """
        response_obj = self.gemini_service.llm_conversation(query, user_id)
        return response_obj['response']

    def store_memory(self, user_id: int, memory_text: str, memory_type: str = "user_info", metadata: Optional[Dict[str, Any]] = None) -> int:
        stored_memories = self.memory_service.add_memory(user_id, memory_text, memory_type, metadata)
        if stored_memories:
            for stored_memory in stored_memories:
                if stored_memory['event'] == 'ADD':
                    self.db.store_memory(user_id, None, stored_memory['id'], stored_memory['memory'])
                elif stored_memory['event'] == 'UPDATE':
                    self.db.update_memory(None, stored_memory['id'], stored_memory['memory'])
                elif stored_memory['event'] == 'DELETE':
                    self.db.delete_memory(stored_memory['id'])
        return None

    def process_media_files(self, message_id: int, data: Dict[str, Any]) -> List[MediaFile]:
        media_files = []
        num_media = int(data.get('NumMedia', 0))
        
        # Create tmp directory if it doesn't exist
        tmp_dir = os.path.join(os.getcwd(), 'tmp')
        os.makedirs(tmp_dir, exist_ok=True)
        
        try:
            for i in range(num_media):
                media_url = data.get(f'MediaUrl{i}')
                content_type = data.get(f'MediaContentType{i}')
                
                if media_url:
                    media_file = self.process_single_media_file(message_id, media_url, content_type, tmp_dir)
                    if media_file:
                        media_files.append(media_file)
                    
        except Exception as e:
            logger.error(f"Error processing media files: {e}")
            # Clean up any downloaded files
            self.cleanup_tmp_files(tmp_dir)
            raise
        
        # Clean up tmp files after processing
        self.cleanup_tmp_files(tmp_dir)
        
        return media_files

    def process_single_media_file(self, message_id: int, media_url: str, content_type: str, tmp_dir: str) -> MediaFile:
        try:
            # Generate unique filename
            file_extension = self.get_file_extension_from_content_type(content_type)
            unique_id = str(uuid.uuid4())
            filename = f"{unique_id}{file_extension}"
            tmp_file_path = os.path.join(tmp_dir, filename)
            
            # Download media file to tmp directory
            self.twilio_service.download_media(media_url, tmp_file_path)
            
            # Calculate file hash and size
            file_hash = self.file_service.calculate_file_hash(tmp_file_path)
            file_size = self.file_service.get_file_size(tmp_file_path)

            # if file_hash is already in the database, then return the media_file_id
            media_file = self.db.get_media_file_by_hash(file_hash)

            # if media_file_id is not None, then associate the media file with the message
            if media_file:
                self.db.associate_media_with_message(message_id, media_file.id)
                self.db.increment_forwarded_count(media_file.id)
                return media_file
            
            # Generate S3 key with timestamp and unique ID
            timestamp = datetime.now().strftime('%Y/%m/%d')
            s3_key = f"media/{timestamp}/{unique_id}{file_extension}"
            
            # Upload to object storage
            s3_url = self.file_service.upload_file(tmp_file_path, s3_key, content_type)
            
            if not s3_url:
                raise Exception("Failed to upload file to object storage")
            
            # Extract media SID from URL if possible
            media_sid = self.extract_media_sid_from_url(media_url)
            
            signed_url = self.file_service.get_signed_url(s3_key)

            description = self.gemini_service.analyze_media(signed_url, content_type)

            # Store media file independently
            media_file = self.db.store_media_file(
                media_sid=media_sid,
                content_type=content_type,
                file_size=file_size,
                file_hash=file_hash,
                s3_key=s3_key,
                s3_url=s3_url,
                description=description
            )
            
            # Associate the media file with the message
            self.db.associate_media_with_message(message_id, media_file.id)
            
            return media_file
            
        except Exception as e:
            logger.error(f"Error processing media file {media_url}: {e}")
            # Clean up tmp file if it exists
            try:
                if 'tmp_file_path' in locals() and os.path.exists(tmp_file_path):
                    os.remove(tmp_file_path)
            except Exception:
                pass
            raise

    def cleanup_tmp_files(self, tmp_dir: str):
        """Clean up temporary files."""
        try:
            if os.path.exists(tmp_dir):
                for file in os.listdir(tmp_dir):
                    file_path = os.path.join(tmp_dir, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        logger.debug(f"Cleaned up tmp file: {file_path}")
        except Exception as e:
            logger.warning(f"Error cleaning up tmp files: {e}")

    @staticmethod
    def get_file_extension_from_content_type(content_type: str) -> str:
        """Get file extension from MIME type."""
        extension_map = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
            'video/mp4': '.mp4',
            'video/quicktime': '.mov',
            'audio/mpeg': '.mp3',
            'audio/ogg': '.ogg',
            'audio/wav': '.wav',
            'application/pdf': '.pdf',
            'text/plain': '.txt'
        }
        return extension_map.get(content_type, '.bin')

    @staticmethod
    def extract_media_sid_from_url(media_url: str) -> str:
        """Extract media SID from Twilio media URL."""
        try:
            # Twilio media URLs typically end with the media SID
            # e.g., https://api.twilio.com/.../Media/ME123456789
            parts = media_url.split('/')
            if len(parts) > 0 and parts[-1].startswith('ME'):
                return parts[-1]
            return media_url.split('/')[-1] if '/' in media_url else media_url
        except Exception:
            return media_url

    def get_formatted_past_interactions(self, user_id: int, limit: int = 10) -> str:
        past_interactions = self.db.get_interactions_by_user_id(user_id, limit)[::-1]
        formatted_interactions = []
        for interaction in past_interactions:
            formatted_interactions.append(
                f"{interaction['id']}. User: {interaction['user_message']}\nBot: {interaction['bot_response']}\n\n"
            )
        return "\n".join(formatted_interactions)
    
    def get_recent_interactions(self, user_id: str, limit: int = 10) -> str:
        interactions = self.db.get_interactions_by_user_id(user_id, limit, detailed=True)
        formatted_interactions = []
        for interaction in interactions:
            formatted_interaction = {
                "id": interaction['id'],
                "user_message": interaction['user_message'],
                "bot_response": interaction['bot_response'],
                "memory_created": interaction["memory_created"],
                "sources": interaction["sources"],
                "original_message_body": interaction['original_message_body'],
                "message_type": interaction['message_type'],
                "media_files": []
            }
            for media_file_s3_key in interaction.get('media_file_s3_keys', []) or []:
                formatted_interaction['media_files'].append(self.file_service.get_signed_url(media_file_s3_key))

            formatted_interactions.append(formatted_interaction)

        return formatted_interactions

    def get_memories_by_user_id(self, user_details: Dict[str, Any]) -> List[Dict[str, Any]]:

        memories = self.db.get_all_memories_with_user_info(user_details['id'])
        sourced_memories = self.db.get_sourced_memories(user_details['id'])
        
        formatted_memories = []
        for memory in memories:
            formatted_memory = {
                "raw_message_id": memory['raw_message_id'],
                "original_message_body": memory.get('original_message_body'),
                "memories": memory.get('memories'),
                "media_files": []
            }
            for media_file_s3_key in memory.get('media_file_s3_keys', []) or []:
                formatted_memory['media_files'].append(self.file_service.get_signed_url(media_file_s3_key))

            formatted_memories.append(formatted_memory)
        
        return {
            "user_info": {
                "user_id": user_details['id'],
                "whatsapp_id": user_details['whatsapp_id'],
                "phone_number": user_details['phone_number'],
                "profile_name": user_details['profile_name'],
                "timezone": user_details['timezone']
            },
            "memories_count": len(formatted_memories),
            "memories": formatted_memories,
            "sourced_memories": sourced_memories
        }