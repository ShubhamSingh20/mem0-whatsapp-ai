# WhatsApp AI Memory Bot

A production-ready WhatsApp AI chatbot with intelligent memory management, built with FastAPI, PostgreSQL, and Mem0. The system handles media processing, maintains conversation context, and implements robust data integrity patterns.

## Core Technical Approaches

### 🔄 Idempotency & Duplicate Prevention

**Message Processing Idempotency**
- Uses `message_sid` (Twilio's unique identifier) as the primary deduplication key
- Database method `get_raw_message_by_sid()` checks for existing messages before processing
- Returns existing message IDs instead of creating duplicates when webhooks are retried
- Prevents double-processing of the same WhatsApp message across webhook retries

**Memory Storage Idempotency** 
- `store_memory()` checks for existing memories linked to the same `raw_message_id`
- Returns existing memory IDs when duplicates are detected
- Prevents creating multiple memory entries for the same conversation turn
- Direct memory creation via API uses separate `store_memory_direct()` method

**Media File Deduplication**
- Uses SHA256 file hashing to detect identical media content
- `store_media_file()` checks for existing files with the same `file_hash`
- Increments `forwarded_count` instead of storing duplicate files
- Saves storage costs and maintains referential integrity

### 🌍 Timezone Handling

**Automatic Timezone Detection**
- Uses `phonenumbers` library to infer timezone from WhatsApp phone numbers
- `infer_timezone_from_number()` extracts country-specific timezone (e.g., `Asia/Kolkata`)
- Stores user timezone in the `users` table for consistent time calculations

**UTC Standardization**
- All database timestamps stored in UTC using PostgreSQL's `CURRENT_TIMESTAMP`
- Memory metadata includes UTC timestamps for consistent cross-timezone querying
- Gemini service converts user-local time queries to UTC for accurate memory filtering

**Time-based Memory Queries**
- LLM function calls can specify date ranges in user's local timezone
- Automatic conversion from user timezone to UTC for database queries
- Supports queries like "meetings this week" with proper timezone context

### 📊 Data Integrity Patterns

**Unique Constraints**
- `message_sid` ensures no duplicate message processing
- `phone_number` prevents multiple user accounts for same WhatsApp number
- `mem0_id` maintains one-to-one mapping between local and Mem0 memories

**Cascading Deletes**
- User deletion cascades to messages, memories, and interactions
- Raw message deletion automatically removes associated memories
- Maintains referential integrity across the entire data model

**Connection Pooling & Retry Logic**
- PostgreSQL connection pooling prevents connection exhaustion
- Automatic retry on `psycopg2.OperationalError` for connection recovery
- Graceful handling of database connection failures

## Installation & Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment variables**
   - Set up PostgreSQL connection details in `configs.py`
   - Add Mem0 API key for memory management
   - Configure Gemini API for AI processing
   - Set up Twilio credentials for WhatsApp integration

3. **Initialize database**
   ```bash
   # Run migrations in order
   psql -d your_db -f migrations/001_create_users.sql
   psql -d your_db -f migrations/002_create_raw_message.sql
   psql -d your_db -f migrations/003_create_media.sql
   psql -d your_db -f migrations/004_create_memories.sql
   psql -d your_db -f migrations/005_create_interactions.sql
   ```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/webhook` | WhatsApp webhook for message processing |
| POST | `/memories` | Create memory for a user |
| GET | `/memories` | Search/retrieve user memories |
| POST | `/memories/list` | List all memories for a user |

## Key Features

- **Intelligent Memory Management**: Automatically stores and retrieves conversation context using Mem0
- **Media Processing**: Handles images, videos, audio with Gemini analysis and cloud storage
- **Duplicate Prevention**: Robust idempotency ensures no data duplication across webhook retries
- **Timezone Awareness**: Automatic timezone detection and proper UTC conversion for global users
- **Production Ready**: Connection pooling, error handling, and comprehensive logging

## Architecture Benefits

- **Data Consistency**: Idempotent operations prevent corruption from retries/failures
- **Storage Efficiency**: File deduplication reduces cloud storage costs
- **Global Support**: Proper timezone handling for international users
- **Scalability**: Connection pooling and efficient database queries support high load
- **Reliability**: Comprehensive error handling and graceful degradation

## Development Notes

This system demonstrates production-level patterns for:
- Webhook idempotency in distributed systems
- Content-based deduplication strategies  
- Cross-timezone data handling
- Robust database connection management
- AI-powered conversation memory
