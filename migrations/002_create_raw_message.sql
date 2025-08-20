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
