# 🧠 Bot Memory System Features

## Overview
The Discord bot now includes an advanced memory system that can remember conversations and user personalities, making interactions more personalized and contextual. The bot can also reply to specific messages and track conversation threads.

## Memory Files
- **`brain_chat_memory.txt`** - Stores chat history with timestamps and reply relationships
- **`user_personalities.json`** - Stores user personality data and preferences

## Features

### 1. Chat Memory
- **Automatic Storage**: Every conversation is automatically saved with timestamps
- **Context Awareness**: AI uses recent chat history to provide more relevant responses
- **Persistent Storage**: Chat history survives bot restarts
- **Size Management**: Automatically limits memory to prevent excessive file sizes
- **Reply Tracking**: Remembers which messages are replies to others

### 2. Message Reply System
- **Reply Detection**: Automatically detects when users reply to messages
- **Context Preservation**: Includes original message context in AI responses
- **Thread Tracking**: Maintains conversation threads and relationships
- **Smart Responses**: AI responds directly to the replied message
- **Memory Integration**: Reply relationships are stored in memory

### 3. User Personality Tracking
- **Message Analysis**: Bot analyzes user messages to detect personality traits
- **Topic Detection**: Identifies user interests (technology, gaming, music, etc.)
- **Interaction History**: Tracks message count, first seen, and last interaction
- **Personalized Responses**: AI uses personality data to tailor responses

### 4. Personality Traits Detected
- **Friendly**: Uses polite language, greetings, thanks
- **Curious**: Asks questions, seeks information
- **Creative**: Discusses ideas, art, design, imagination
- **Technical**: Asks for tutorials, explanations, technical help
- **Humorous**: Uses jokes, humor, comedy

### 5. Topic Categories
- **Technology**: Programming, computers, software, AI
- **Gaming**: Games, players, levels, scores
- **Music**: Songs, artists, concerts, albums
- **Movies**: Films, cinema, actors, directors
- **Food**: Restaurants, cooking, meals
- **Travel**: Trips, vacations, countries, cities
- **Sports**: Teams, matches, players
- **Education**: Learning, schools, courses, books

## Commands

### Memory Commands
- `!profile [@user]` - View user profile and personality data
- `!memory` - Show bot memory statistics
- `!thread [message_id]` - View recent conversations or specific conversation thread
- `!forget [@user]` - Remove user data from memory (Owner only)

### Reply Commands
- `!reply` - Show how to use the reply feature
- `!r` - Alias for reply help

### Example Usage
```
!profile @username
!memory
!thread
!thread 1234567890123456789
!reply
!forget @username
```

## How to Use Reply Feature

### Basic Reply
1. **Right-click** on any message in Discord
2. **Select "Reply"** from the context menu
3. **Type your message** and send
4. **Bot responds** directly to that message with context

### Example Conversation
```
User A: "ใครรู้จัก Python ไหม?"
User B: [Reply] "ผมรู้จักครับ มันเป็นภาษาโปรแกรมมิ่ง"
Bot: [Reply to User B] "ใช่ครับ! Python เป็นภาษาที่ยอดเยี่ยมสำหรับผู้เริ่มต้น..."
```

## AI Integration
The memory system enhances AI responses by:
1. **User Context**: Providing personality and interest information
2. **Chat History**: Including recent conversations with the user
3. **General Context**: Adding recent general chat history
4. **Reply Context**: Including original message when replying
5. **Personalized Prompts**: Tailoring responses based on user preferences

## Automatic Features
- **Periodic Saving**: Memories are saved every 30 minutes
- **Startup Loading**: All memories are loaded when bot starts
- **Shutdown Saving**: Memories are saved before bot shuts down
- **Background Processing**: Memory updates happen in background threads
- **Reply Detection**: Automatic detection and processing of message replies

## Security & Privacy
- **Owner Control**: Only owners can delete user data
- **Local Storage**: All data is stored locally on the bot's server
- **No External Sharing**: Memory data is not shared with external services
- **User Consent**: Users can request their data to be removed

## Technical Details
- **File Format**: JSON for user data, plain text for chat history
- **Encoding**: UTF-8 for proper Thai language support
- **Backup**: Files are automatically managed and cleaned
- **Performance**: Memory operations are optimized for speed
- **Reply Tracking**: Message IDs are stored to maintain thread relationships

## Benefits
1. **Personalized Experience**: Each user gets tailored responses
2. **Context Awareness**: Bot remembers previous conversations
3. **Learning Capability**: Bot learns user preferences over time
4. **Improved Engagement**: More relevant and interesting interactions
5. **Long-term Memory**: Conversations persist across sessions
6. **Thread Continuity**: Maintains conversation flow through replies
7. **Better Organization**: Clear relationship between related messages

## Conversation Threads
The bot can track and display conversation threads:
- **Recent Conversations**: View the latest chat history
- **Specific Threads**: View conversations around specific messages
- **Reply Chains**: Follow the flow of replies and responses
- **Context Preservation**: Maintain conversation context across replies

The memory system makes the bot more intelligent and provides a more engaging user experience by remembering and learning from each interaction, while the reply system ensures conversations flow naturally and maintain context. 