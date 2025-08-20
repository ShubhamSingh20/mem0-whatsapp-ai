from configs import BUCKET_NAME, BUCKET_ACCESS_KEY, BUCKET_SECRET_KEY, BUCKET_URL
import boto3
from botocore.exceptions import ClientError
import os
import hashlib
import mimetypes
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ObjectStorageService:
    def __init__(self, bucket_name=BUCKET_NAME, region_name="auto"):
        self.bucket_name = bucket_name
        self.s3 = boto3.client(
            service_name ="s3",
            endpoint_url = BUCKET_URL,
            aws_access_key_id = BUCKET_ACCESS_KEY,
            aws_secret_access_key = BUCKET_SECRET_KEY,
            region_name="auto"
        )

    def put_object(self, key, data, content_type="text/plain", content_encoding="utf-8"):
        try:
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=data,
                ContentType=content_type,
                ContentEncoding=content_encoding
            )

        except ClientError as e:
            print(f"Failed to upload: {e}")

    def get_object(self, key):
        try:
            response = self.s3.get_object(Bucket=self.bucket_name, Key=key)
            data = response["Body"].read()
            return data
        except ClientError as e:
            print(f"Failed to download: {e}")
            return None

    def get_signed_url(self, key, expiration=3600):
        try:
            key = key.replace(BUCKET_URL + "/", "")
            response = self.s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=expiration,
            )
            return response
        except ClientError as e:
            print(f"Failed to generate signed URL: {e}")
            return None

    def upload_file(self, file_path: str, s3_key: Optional[str] = None, 
                   content_type: Optional[str] = None) -> Optional[str]:
        """
        Upload a file from local filesystem to object storage.
        
        Args:
            file_path: Local path to the file
            s3_key: Custom S3 key (optional, defaults to basename of file)
            content_type: MIME type (optional, auto-detected)
            
        Returns:
            S3 URL if successful, None if failed
        """
        try:
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return None
            
            # Generate S3 key if not provided
            if not s3_key:
                s3_key = os.path.basename(file_path)
            
            # Auto-detect content type if not provided
            if not content_type:
                content_type, _ = mimetypes.guess_type(file_path)
                if not content_type:
                    content_type = "application/octet-stream"
            
            # Upload file
            with open(file_path, 'rb') as file_data:
                self.s3.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=file_data,
                    ContentType=content_type
                )
            
            # Generate public URL
            s3_url = f"{BUCKET_URL}/{s3_key}"
            logger.info(f"Successfully uploaded {file_path} to {s3_url}")
            return s3_url
            
        except ClientError as e:
            logger.error(f"Failed to upload {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error uploading {file_path}: {e}")
            return None

    @staticmethod
    def calculate_file_hash(file_path: str) -> Optional[str]:
        """Calculate SHA256 hash of a file."""
        try:
            hasher = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logger.error(f"Error calculating hash for {file_path}: {e}")
            return None

    @staticmethod
    def get_file_size(file_path: str) -> Optional[int]:
        """Get file size in bytes."""
        try:
            return os.path.getsize(file_path)
        except Exception as e:
            logger.error(f"Error getting size for {file_path}: {e}")
            return None