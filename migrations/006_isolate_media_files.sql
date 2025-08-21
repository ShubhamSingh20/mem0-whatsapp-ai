-- Migration to isolate media files from raw messages
-- This allows the same media file to be reused across multiple messages

-- Step 1: Create the pivot table for many-to-many relationship
CREATE TABLE IF NOT EXISTS message_media (
    id SERIAL PRIMARY KEY,
    raw_message_id INTEGER REFERENCES raw_messages(id) ON DELETE CASCADE,
    media_file_id INTEGER REFERENCES media_files(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(raw_message_id, media_file_id) -- Prevent duplicate associations
);


-- Step 3: Remove the raw_message_id column from media_files
-- First drop the foreign key constraint
ALTER TABLE media_files DROP CONSTRAINT IF EXISTS media_files_raw_message_id_fkey;

-- Then drop the column
ALTER TABLE media_files DROP COLUMN IF EXISTS raw_message_id;

