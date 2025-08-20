from service.mem0_service import Mem0Service
from service.twilio_service import TwilioMediaHelper
from service.gemini_service import GeminiService
from utils import infer_timezone_from_number
from service.object_storage import ObjectStorageService
from service.database import db_service
from models import WhatsappWebhook, User, RawMessage, MessageWithMedia, MediaFile
from typing import Dict, Any, List, Optional
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
    
    def process_whatsapp_message(self, data: WhatsappWebhook) -> MessageWithMedia:
        try:
            message_sid = data.get('MessageSid', '')
            
            # Extract user information from webhook data
            whatsapp_id = data.get('WaId', '')
            phone_number = data.get('From', '').replace('whatsapp:', '')
            profile_name = data.get('ProfileName')
            timezone = infer_timezone_from_number(phone_number)
            
            # Get or create user
            user_id = self.db.get_or_create_user(
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
                # Use existing message data
                raw_message_id = existing_message['id']
                # Get existing media files
                existing_media_files = self.db.get_media_files_by_message_id(raw_message_id)
                media_files = [MediaFile(**media) for media in existing_media_files]
            else:
                # Store new raw message (idempotent method will handle duplicates)
                raw_message_id = self.db.store_raw_message(
                    user_id=user_id,
                    message_sid=message_sid,
                    body=data.get('Body'),
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
                    media_files = self.process_media_files(raw_message_id, data)
            
            # Create model objects
            user = User(
                id=user_id,
                whatsapp_id=whatsapp_id,
                phone_number=phone_number,
                profile_name=profile_name,
                timezone=timezone
            )
            
            raw_message = RawMessage(
                id=raw_message_id,
                user_id=user_id,
                message_sid=message_sid,
                body=data.get('Body'),
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

            message_with_media = MessageWithMedia(
                message=raw_message,
                media_files=media_files,
                user=user
            )
            
            # only explicitly store in mem0 if the message has media files
            if not is_duplicate and len(message_with_media.media_files) > 0:
                mem0_id = self.memory_service.add_memory(message_with_media)
                if mem0_id:
                    self.db.store_memory(user_id, raw_message_id, mem0_id)
                    logger.info(f"Successfully stored new message in mem0 with ID: {mem0_id}")
            

            text_only_message = raw_message.body
            chat_response = ""

            if text_only_message:
                # if text has relevant gemini_service will save it using the memory_service
                response_obj = self.gemini_service.llm_conversation(text_only_message, user_id, user_timezone=user.timezone or "UTC")
                chat_response = response_obj['response']
                print(response_obj)

            # # Storing interaction
            # self.db.store_interaction(user_id, raw_message_id, text_only_message, chat_response, "conversation")

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
        mem0_id = self.memory_service.add_memory_direct(user_id, memory_text, memory_type, metadata)
        if mem0_id:
            self.db.store_memory_direct(user_id, mem0_id)
            return mem0_id
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
        """
        Process a single media file: download, upload to storage, save to DB.
        
        Args:
            message_id: ID of the raw message
            media_url: Twilio media URL
            content_type: MIME type of the media
            tmp_dir: Temporary directory for downloads
            
        Returns:
            MediaFile object
        """
        try:
            # Generate unique filename
            file_extension = self.get_file_extension_from_content_type(content_type)
            unique_id = str(uuid.uuid4())
            filename = f"{unique_id}{file_extension}"
            tmp_file_path = os.path.join(tmp_dir, filename)
            
            # Download media file to tmp directory
            logger.info(f"Downloading media from {media_url}")
            self.twilio_service.download_media(media_url, tmp_file_path)
            
            # Calculate file hash and size
            file_hash = self.file_service.calculate_file_hash(tmp_file_path)
            file_size = self.file_service.get_file_size(tmp_file_path)
            
            # Generate S3 key with timestamp and unique ID
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y/%m/%d')
            s3_key = f"media/{timestamp}/{unique_id}{file_extension}"
            
            # Upload to object storage
            logger.info(f"Uploading {tmp_file_path} to object storage")
            s3_url = self.file_service.upload_file(tmp_file_path, s3_key, content_type)
            
            if not s3_url:
                raise Exception("Failed to upload file to object storage")
            
            # Extract media SID from URL if possible
            media_sid = self.extract_media_sid_from_url(media_url)
            
            signed_url = self.file_service.get_signed_url(s3_key)

            description = self.gemini_service.analyze_media(signed_url, content_type)

            # Store in database
            media_file_id = self.db.store_media_file(
                raw_message_id=message_id,
                media_sid=media_sid,
                content_type=content_type,
                file_size=file_size,
                file_hash=file_hash,
                s3_key=s3_key,
                s3_url=s3_url,
                description=description
            )
            
            # Create MediaFile object
            media_file = MediaFile(
                id=media_file_id,
                raw_message_id=message_id,
                media_sid=media_sid,
                content_type=content_type,
                file_size=file_size,
                file_hash=file_hash,
                s3_key=s3_key,
                s3_url=s3_url,
                description=description
            )
            
            logger.info(f"Successfully processed media file: {media_file_id}")
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
        
    
    def get_memories_by_user_id(self, user_details: Dict[str, Any]) -> List[Dict[str, Any]]:

        memories = self.db.get_all_memories_with_user_info(user_details['id'])
        
        formatted_memories = []
        for memory in memories:
            formatted_memory = {
                "id": memory['id'],
                "mem0_id": memory['mem0_id'],
                "raw_message_id": memory['raw_message_id'],
                "created_at": memory['created_at'].isoformat() if memory['created_at'] else None,
                "updated_at": memory['updated_at'].isoformat() if memory['updated_at'] else None,
                "original_message_body": memory.get('original_message_body'),
                "message_type": memory.get('message_type')
            }
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
            "memories": formatted_memories
        }