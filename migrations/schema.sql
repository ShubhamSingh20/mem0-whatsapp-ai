-- Users table to store WhatsApp user information
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    whatsapp_id VARCHAR(50) UNIQUE NOT NULL,
    phone_number VARCHAR(20) NOT NULL UNIQUE,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    profile_name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS memories (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    mem0_infered_memory TEXT,
    raw_message_id INTEGER REFERENCES raw_messages(id) ON DELETE CASCADE,
    mem0_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw_messages (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    message_sid VARCHAR(100) UNIQUE NOT NULL,
    sms_message_sid VARCHAR(100),
    body TEXT,
    message_type VARCHAR(20) DEFAULT 'text', -- text, image, video, audio, document
    from_number VARCHAR(50) NOT NULL,
    to_number VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'received',
    num_media INTEGER DEFAULT 0,
    account_sid VARCHAR(100),
    api_version VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_data JSONB -- Store the complete webhook payload
);

CREATE TABLE IF NOT EXISTS media_files (
    id SERIAL PRIMARY KEY,
    media_sid VARCHAR(100),
    content_type VARCHAR(100),
    forwarded_count INTEGER DEFAULT 0,
    description TEXT DEFAULT NULL,
    file_size BIGINT,
    file_hash VARCHAR(64), -- SHA256 hash for deduplication
    s3_key VARCHAR(500), -- S3/R2 storage key
    s3_url TEXT, -- Public URL if available
    is_duplicate BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS message_media (
    id SERIAL PRIMARY KEY,
    raw_message_id INTEGER REFERENCES raw_messages(id) ON DELETE CASCADE,
    media_file_id INTEGER REFERENCES media_files(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(raw_message_id, media_file_id) -- Prevent duplicate associations
);



CREATE TABLE IF NOT EXISTS interactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    raw_message_id INTEGER REFERENCES raw_messages(id) ON DELETE CASCADE,
    memory_id INTEGER REFERENCES memories(id) ON DELETE CASCADE,

    user_message TEXT NOT NULL,
    bot_response TEXT,
    
    interaction_type interaction_type_enum DEFAULT 'conversation',

    sources TEXT[] DEFAULT '{}',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE interactions ADD CONSTRAINT unique_interaction_per_message 
UNIQUE (raw_message_id);

