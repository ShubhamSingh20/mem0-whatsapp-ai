CREATE TABLE IF NOT EXISTS media_files (
    id SERIAL PRIMARY KEY,
    raw_message_id INTEGER REFERENCES raw_messages(id) ON DELETE CASCADE,
    media_sid VARCHAR(100),
    content_type VARCHAR(100),
    forwarded_count INTEGER DEFAULT 0,
    description TEXT DEFAULT NULL,
    file_size BIGINT,
    file_hash VARCHAR(64), -- SHA256 hash for deduplication
    s3_key VARCHAR(500), -- S3/R2 storage key
    s3_url TEXT, -- Public URL if available
    is_duplicate BOOLEAN DEFAULT FALSE,
    original_media_id INTEGER REFERENCES media_files(id), -- Reference to original if duplicate
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);