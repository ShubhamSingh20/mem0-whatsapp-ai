-- Interactions table to store user-bot interactions with memory operations

-- enum for interaction type
CREATE TYPE interaction_type_enum AS ENUM ('conversation', 'api_call');

CREATE TABLE IF NOT EXISTS interactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    raw_message_id INTEGER REFERENCES raw_messages(id) ON DELETE CASCADE,
    memory_id INTEGER REFERENCES memories(id) ON DELETE CASCADE,

    user_message TEXT NOT NULL,
    bot_response TEXT,
    
    interaction_type interaction_type_enum DEFAULT 'conversation',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
