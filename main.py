import os
import json
import re
import asyncio
import psutil
import datetime
import sys
import logging
import logging.handlers
import subprocess
import concurrent.futures
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from dataclasses import dataclass
from typing import List, Dict, Any
import yt_dlp
from github import Github
import random

import discord
from discord.ext import commands, tasks

# --- Force working directory to W:\\Code\\Bot Discord ---
try:
    desired_cwd = r"W:\Code\Bot Discord"
    if os.getcwd() != desired_cwd:
        os.chdir(desired_cwd)
except Exception as e:
    print(f"[Startup Warning] Could not set working directory: {e}")

# --- Disk Space Management ---
def get_disk_usage():
    """Get current disk usage in MB for the bot directory"""
    try:
        total_size = 0
        for dirpath, dirnames, filenames in os.walk('.'):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except (OSError, FileNotFoundError):
                    continue
        return total_size / (1024 * 1024)  # Convert to MB
    except Exception as e:
        logger.error(f"Error calculating disk usage: {e}")
        return 0

def get_directory_size(directory):
    """Get size of a specific directory in MB"""
    try:
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except (OSError, FileNotFoundError):
                    continue
        return total_size / (1024 * 1024)  # Convert to MB
    except Exception as e:
        logger.error(f"Error calculating directory size: {e}")
        return 0

def cleanup_old_files():
    """Clean up old files to save disk space"""
    try:
        # Clean up old log files (keep only last 3)
        log_files = [f for f in os.listdir('.') if f.startswith('bot.log')]
        if len(log_files) > 3:
            log_files.sort()
            for old_log in log_files[:-3]:
                try:
                    os.remove(old_log)
                    print(f"Removed old log file: {old_log}")
                except:
                    pass
        
        # Clean up any temporary files
        temp_files = [f for f in os.listdir('.') if f.endswith('.tmp') or f.endswith('.temp')]
        for temp_file in temp_files:
            try:
                os.remove(temp_file)
                print(f"Removed temp file: {temp_file}")
            except:
                pass
    except Exception as e:
        print(f"Error during cleanup: {e}")

# --- Logging Setup ---
def setup_logging():
    """Setup logging with rotation to save disk space"""
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Configure rotating file handler (max 1MB per file, keep 3 files)
    file_handler = logging.handlers.RotatingFileHandler(
        'logs/bot.log',
        maxBytes=1024*1024,  # 1MB
        backupCount=3,
        encoding='utf-8'
    )
    
    # Configure console handler
    console_handler = logging.StreamHandler()
    
    # Set formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Reduce verbosity of external libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('discord').setLevel(logging.WARNING)
    
    return logger

logger = setup_logging()

# --- Memory Management System ---
class MemoryManager:
    def __init__(self):
        self.chat_memory_file = "brain_chat_memory.txt"
        self.user_memory_file = "user_personalities.json"
        # Reduced limits to save disk space
        self.max_memory_entries = 200  # Reduced from 1000
        self.max_user_memory = 20      # Reduced from 50
        self.max_chat_length = 500     # Max characters per chat entry
        self.chat_history = []
        self.user_personalities = {}
        self.load_memories()
    
    def load_memories(self):
        """Load chat history and user personalities from files."""
        try:
            # Load chat memory
            if os.path.exists(self.chat_memory_file):
                with open(self.chat_memory_file, 'r', encoding='utf-8') as f:
                    self.chat_history = [line.strip() for line in f.readlines() if line.strip()]
                logger.info(f"Loaded {len(self.chat_history)} chat memory entries")
            
            # Load user personalities
            if os.path.exists(self.user_memory_file):
                with open(self.user_memory_file, 'r', encoding='utf-8') as f:
                    self.user_personalities = json.load(f)
                logger.info(f"Loaded {len(self.user_personalities)} user personalities")
        except Exception as e:
            logger.error(f"Error loading memories: {e}")
    
    def save_memories(self):
        """Save chat history and user personalities to files."""
        try:
            # Check disk space before saving
            if get_disk_usage() > 500:  # If bot files using more than 500MB
                self._cleanup_memories()
            
            # Save chat memory
            with open(self.chat_memory_file, 'w', encoding='utf-8') as f:
                for entry in self.chat_history[-self.max_memory_entries:]:
                    f.write(entry + '\n')
            
            # Save user personalities
            with open(self.user_memory_file, 'w', encoding='utf-8') as f:
                json.dump(self.user_personalities, f, indent=1, ensure_ascii=False)  # Reduced indent
            
            logger.info("Memories saved successfully")
        except Exception as e:
            logger.error(f"Error saving memories: {e}")
    
    def _cleanup_memories(self):
        """Clean up memories to save disk space"""
        # Reduce chat history
        if len(self.chat_history) > self.max_memory_entries // 2:
            self.chat_history = self.chat_history[-self.max_memory_entries // 2:]
        
        # Remove old user data
        current_time = datetime.datetime.now()
        users_to_remove = []
        for user_id, user_data in self.user_personalities.items():
            try:
                last_interaction = datetime.datetime.fromisoformat(user_data.get('last_interaction', '2000-01-01'))
                if (current_time - last_interaction).days > 30:  # Remove users inactive for 30+ days
                    users_to_remove.append(user_id)
            except:
                users_to_remove.append(user_id)
        
        for user_id in users_to_remove:
            del self.user_personalities[user_id]
        
        if users_to_remove:
            logger.info(f"Cleaned up {len(users_to_remove)} inactive users")
    
    def add_chat_memory(self, user_id: str, username: str, message: str, response: str, replied_to_id: str = None):
        """Add a conversation to chat memory with length limits."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Truncate long messages to save space
        message = message[:200] if len(message) > 200 else message
        response = response[:200] if len(response) > 200 else response
        
        entry = f"[{timestamp}] {username}: {message} | Bot: {response}"
        if replied_to_id:
            entry += f" | Reply: {replied_to_id}"
        
        # Limit entry length
        if len(entry) > self.max_chat_length:
            entry = entry[:self.max_chat_length] + "..."
        
        self.chat_history.append(entry)
        
        # Keep only the latest entries
        if len(self.chat_history) > self.max_memory_entries:
            self.chat_history = self.chat_history[-self.max_memory_entries:]
    
    def update_user_personality(self, user_id: str, username: str, message: str, response: str):
        """Update user personality based on their messages and bot responses."""
        if user_id not in self.user_personalities:
            self.user_personalities[user_id] = {
                "username": username,
                "first_seen": datetime.datetime.now().isoformat(),
                "message_count": 0,
                "topics": {},
                "personality_traits": [],
                "last_interaction": datetime.datetime.now().isoformat()
            }
        
        user_data = self.user_personalities[user_id]
        user_data["message_count"] += 1
        user_data["last_interaction"] = datetime.datetime.now().isoformat()
        user_data["username"] = username  # Update username in case it changed
        
        # Analyze message for topics and personality traits
        self._analyze_message_for_personality(user_id, message)
    
    def _analyze_message_for_personality(self, user_id: str, message: str):
        """Analyze message to extract personality traits and topics."""
        user_data = self.user_personalities[user_id]
        message_lower = message.lower()
        
        # Simple topic detection
        topics = {
            "technology": ["tech", "computer", "programming", "code", "software", "ai", "bot"],
            "gaming": ["game", "play", "gaming", "player", "level", "score"],
            "music": ["music", "song", "artist", "band", "concert", "album"],
            "movies": ["movie", "film", "watch", "cinema", "actor", "director"],
            "food": ["food", "eat", "cook", "restaurant", "meal", "hungry"],
            "travel": ["travel", "trip", "vacation", "visit", "country", "city"],
            "sports": ["sport", "game", "team", "player", "match", "win"],
            "education": ["study", "learn", "school", "university", "course", "book"]
        }
        
        for topic, keywords in topics.items():
            if any(keyword in message_lower for keyword in keywords):
                if topic not in user_data["topics"]:
                    user_data["topics"][topic] = 0
                user_data["topics"][topic] += 1
        
        # Simple personality trait detection
        traits = {
            "friendly": ["hello", "hi", "thanks", "thank you", "please", "nice"],
            "curious": ["what", "how", "why", "when", "where", "question"],
            "creative": ["imagine", "create", "design", "art", "creative", "idea"],
            "technical": ["how to", "tutorial", "guide", "explain", "technical"],
            "humorous": ["joke", "funny", "lol", "haha", "humor", "comedy"]
        }
        
        for trait, keywords in traits.items():
            if any(keyword in message_lower for keyword in keywords):
                if trait not in user_data["personality_traits"]:
                    user_data["personality_traits"].append(trait)
    
    def get_user_context(self, user_id: str) -> str:
        """Get context about a user for AI responses."""
        if user_id not in self.user_personalities:
            return ""
        
        user_data = self.user_personalities[user_id]
        context_parts = []
        
        # Add basic info
        context_parts.append(f"User: {user_data['username']}")
        context_parts.append(f"Messages: {user_data['message_count']}")
        
        # Add personality traits
        if user_data["personality_traits"]:
            traits = ", ".join(user_data["personality_traits"])
            context_parts.append(f"Personality: {traits}")
        
        # Add top topics
        if user_data["topics"]:
            top_topics = sorted(user_data["topics"].items(), key=lambda x: x[1], reverse=True)[:3]
            topics_str = ", ".join([f"{topic} ({count})" for topic, count in top_topics])
            context_parts.append(f"Interests: {topics_str}")
        
        return " | ".join(context_parts)
    
    def get_recent_chat_context(self, limit: int = 5) -> str:  # Reduced from 10
        """Get recent chat history for context."""
        recent = self.chat_history[-limit:] if self.chat_history else []
        return "\n".join(recent)
    
    def get_user_chat_history(self, user_id: str, limit: int = 3) -> str:  # Reduced from 5
        """Get recent chat history for a specific user."""
        user_entries = []
        for entry in self.chat_history[-25:]:  # Reduced from 50
            if f"({user_id})" in entry:
                user_entries.append(entry)
                if len(user_entries) >= limit:
                    break
        return "\n".join(user_entries)

    def get_conversation_thread(self, message_id: str, limit: int = 5) -> List[str]:  # Reduced from 10
        """Get conversation thread around a specific message."""
        thread = []
        for entry in self.chat_history[-50:]:  # Reduced from 100
            if message_id in entry:
                thread.append(entry)
                if len(thread) >= limit:
                    break
        return thread

# --- Configuration ---
@dataclass
class Config:
    discord_bot_token: str = "MTExNDQyMzA5OTAxMDYwMTA5MA.Gf51xv.paxCYDym8E0smYtI6Ua4-2DyBmLBG_bPjOTDyM"
    command_prefix: str = os.getenv("COMMAND_PREFIX", "!")
    max_retries: int = 3
    timeout: float = 30.0

    def __post_init__(self):
        if not self.discord_bot_token:
            raise ValueError("DISCORD_BOT_TOKEN is required")

# --- Response Templates ---
class ResponseTemplates:
    SWEAR_WORDS: List[str] = [
        "เหี้ย", "สัส", "ไอ้สัตว์", "ควย", "ส้นตีน", "กาก", "ชิบหาย",
        "เอ๊ย", "ไอ้บ้า", "โง่", "ควาย", "ห่า"
    ]
    SYSTEM_PROMPT = (
        "You are a helpful AI assistant with memory. You can remember conversations and user personalities. "
        "Use this information to provide more personalized and contextual responses. "
        "Always respond in a friendly and helpful manner."
    )
    ERROR_MESSAGES = {
        "api_error": "ระบบ AI มีปัญหา ลองใหม่อีกครั้ง!",
        "network_error": "เชื่อมต่อไม่ได้ ตรวจสอบอินเทอร์เน็ต!",
        "general_error": "เกิดข้อผิดพลาด กรุณาลองใหม่!"
    }

# --- Ignore Keywords ---
IGNORE_KEYWORDS = ["wom", "วอม", "วอร์ม","@stty_","@stty1_","เกิดข้อผิดพลาด กรุณาลองใหม่","!เกิดข้อผิดพลาด กรุณาลองใหม่","เกิดข้อผิดพลาด กรุณาลองเก","@root@stty:~$","เกิดข้อผิดพลาด กรุณาลองเป"]

# --- URL Detection and Web Reading ---
URL_PATTERN = re.compile(
    r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
)

def is_valid_url(url: str) -> bool:
    """Check if a URL is valid."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def extract_urls(text: str) -> List[str]:
    """Extract URLs from text."""
    urls = URL_PATTERN.findall(text)
    return [url for url in urls if is_valid_url(url)]

def scrape_website_sync(url: str) -> str:
    """Synchronous: Scrapes website content. Runs in a thread."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove unwanted elements
        for element in soup(["script", "style", "nav", "header", "footer", "aside", "iframe", "form"]):
            element.decompose()
        
        # Extract structured information
        title = ""
        author = ""
        date = ""
        main_content = ""
        
        # Try to find title
        title_elem = soup.find('title')
        if title_elem:
            title = title_elem.get_text().strip()
        
        # Try to find article title
        article_title = soup.find(['h1', 'h2'], class_=re.compile(r'title|headline|article-title'))
        if article_title:
            title = article_title.get_text().strip()
        
        # Try to find author
        author_elem = soup.find(['span', 'div', 'p'], class_=re.compile(r'author|byline|writer'))
        if author_elem:
            author = author_elem.get_text().strip()
        
        # Try to find date
        date_elem = soup.find(['time', 'span', 'div'], class_=re.compile(r'date|time|published'))
        if date_elem:
            date = date_elem.get_text().strip()
        
        # Extract main content - try multiple strategies
        # Strategy 1: Look for article content
        article = soup.find(['article', 'main', 'div'], class_=re.compile(r'article|content|post|entry'))
        if article:
            main_content = article.get_text()
        else:
            # Strategy 2: Look for content areas
            content_div = soup.find(['div', 'section'], class_=re.compile(r'content|body|text|post'))
            if content_div:
                main_content = content_div.get_text()
            else:
                # Strategy 3: Fallback to body text
                main_content = soup.get_text()
        
        # Clean up the content
        lines = (line.strip() for line in main_content.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        main_content = ' '.join(chunk for chunk in chunks if chunk and len(chunk) > 10)
        
        # Limit content length but keep more than before
        if len(main_content) > 5000:
            main_content = main_content[:5000] + "... [เนื้อหาถูกตัดเพื่อความกระชับ]"
        
        # Compose structured summary
        summary = ""
        if title:
            summary += f"**📰 หัวข้อ:** {title}\n\n"
        if author:
            summary += f"**✍️ ผู้เขียน:** {author}\n"
        if date:
            summary += f"**📅 วันที่:** {date}\n"
        if author or date:
            summary += "\n"
        
        summary += f"**📄 เนื้อหาหลัก:**\n{main_content}"
        
        return summary
        
    except requests.exceptions.RequestException as e:
        return f"❌ ไม่สามารถเชื่อมต่อกับเว็บไซต์ได้: {str(e)}"
    except Exception as e:
        return f"❌ เกิดข้อผิดพลาดในการอ่านเว็บไซต์: {str(e)}"

# --- Owner Check ---
OWNER_USERNAMES = ["stty_", "stty1_"]

def is_owner(ctx):
    """Check if the command author is an owner."""
    return ctx.author.name in OWNER_USERNAMES

async def is_admin(ctx):
    """Check if the command author is an admin/owner."""
    return ctx.author.name in OWNER_USERNAMES

def is_owner_mentioned(message_content: str) -> bool:
    """Check if any owner is mentioned in the message."""
    message_lower = message_content.lower()
    return any(owner.lower() in message_lower for owner in OWNER_USERNAMES)

# --- AI Service using OpenAI with Function Calling and Grok-3 Fallback ---
class AIService:
    def __init__(self, executor: concurrent.futures.ThreadPoolExecutor, memory_manager, system_prompt: str = ""):
        self.system_prompt = system_prompt
        self.executor = executor
        self.memory_manager = memory_manager
        
        # OpenAI configuration
        self.openai_endpoint = "https://models.github.ai/inference/"
        self.openai_model = "openai/gpt-4.1"
        self.openai_api_key = "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"
        
        # Grok-3 configuration (fallback)
        self.grok_endpoint = "https://models.github.ai/inference"
        self.grok_model = "xai/grok-3"
        self.grok_api_key = "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"
        
        self.timeout = 30
        self._initialize_ai_services()
        
        # Define available functions
        self.available_functions = {
            "getFlightInfo": self.get_flight_info
        }
        
        # Define function schemas
        self.function_schemas = [
            {
                "type": "function",
                "function": {
                    "name": "getFlightInfo",
                    "description": "Returns information about the next flight between two cities. This includes the name of the airline, flight number and the date and time of the next flight",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "originCity": {
                                "type": "string",
                                "description": "The name of the city where the flight originates",
                            },
                            "destinationCity": {
                                "type": "string", 
                                "description": "The flight destination city",
                            },
                        },
                        "required": [
                            "originCity",
                            "destinationCity"
                        ],
                    }
                }
            }
        ]

    def _initialize_ai_services(self):
        """Initialize AI services."""
        try:
            logger.info(f"OpenAI initialized with endpoint: {self.openai_endpoint}")
            logger.info(f"OpenAI model: {self.openai_model}")
            logger.info(f"Grok-3 fallback initialized with endpoint: {self.grok_endpoint}")
            logger.info(f"Grok-3 model: {self.grok_model}")
        except Exception as e:
            logger.error(f"Error initializing AI services: {e}")

    def get_flight_info(self, data):
        """Function to get flight information between two cities."""
        origin_city = data.get("originCity", "")
        destination_city = data.get("destinationCity", "")
        
        if origin_city == "Seattle" and destination_city == "Miami":
            return json.dumps({
                "airline": "Delta",
                "flight_number": "DL123",
                "flight_date": "May 7th, 2024",
                "flight_time": "10:00AM"
            })
        return json.dumps({"error": "No flights found between the cities"})

    def set_system_prompt(self, prompt: str):
        self.system_prompt = prompt

    async def get_response(self, user_message: str, user_id: str = None, username: str = None, image_urls: list = None) -> str:
        """Get AI response using OpenAI with Grok-3 fallback."""
        if not self.openai_api_key or self.openai_api_key == "YOUR_GITHUB_TOKEN_HERE":
            return "🤖 GitHub token is not configured. Please set a valid GITHUB_TOKEN."
        
        def sync_openai_call():
            try:
                # Build context-aware prompt
                context_prompt = self.system_prompt
                if user_id and username and self.memory_manager:
                    user_context = self.memory_manager.get_user_context(user_id)
                    user_history = self.memory_manager.get_user_chat_history(user_id, 2)
                    if user_context:
                        context_prompt += f"\nUser context: {user_context}"
                    if user_history:
                        context_prompt += f"\nRecent chat: {user_history}"
                
                # Prepare messages
                messages = [
                    {"role": "system", "content": context_prompt or "You are a helpful AI assistant with memory and function calling capabilities."},
                    {"role": "user", "content": user_message}
                ]
                
                # Make OpenAI API call with function calling
                headers = {
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json"
                }
                
                body = {
                    "model": self.openai_model,
                    "messages": messages,
                    "tools": self.function_schemas,
                    "max_tokens": 1000,
                    "temperature": 0.7
                }
                
                response = requests.post(f"{self.openai_endpoint}/chat/completions", headers=headers, json=body, timeout=self.timeout)
                
                if response.status_code == 429:
                    # Rate limit exceeded - return special indicator
                    error_data = response.json()
                    wait_seconds = error_data.get("error", {}).get("details", "").split("wait ")[-1].split(" ")[0] if "wait " in error_data.get("error", {}).get("details", "") else "unknown"
                    logger.warning(f"OpenAI rate limit exceeded. Wait {wait_seconds} seconds before retrying.")
                    return f"RATE_LIMIT_EXCEEDED:{wait_seconds}"
                
                elif response.status_code == 400:
                    error_data = response.json()
                    error_message = error_data.get("error", {}).get("message", "Unknown error")
                    logger.error(f"OpenAI API error: {response.status_code} {error_message}")
                    return f"OPENAI_ERROR:{error_message}"
                
                elif response.status_code != 200:
                    logger.error(f"OpenAI API error: {response.status_code} {response.text}")
                    return f"OPENAI_ERROR:{response.status_code}"
                
                response_data = response.json()
                
                # Handle function calls if needed
                if response_data.get("choices") and response_data["choices"][0].get("finish_reason") == "tool_calls":
                    # Append the model response to the chat history
                    messages.append(response_data["choices"][0]["message"])
                    
                    # Handle tool calls
                    if response_data["choices"][0]["message"].get("tool_calls"):
                        for tool_call in response_data["choices"][0]["message"]["tool_calls"]:
                            if tool_call.get("type") == "function":
                                # Parse the function call arguments
                                function_args = json.loads(tool_call["function"]["arguments"])
                                logger.info(f"Calling function `{tool_call['function']['name']}` with arguments {tool_call['function']['arguments']}")
                                
                                # Call the function
                                if tool_call["function"]["name"] in self.available_functions:
                                    function_return = self.available_functions[tool_call["function"]["name"]](function_args)
                                    logger.info(f"Function returned = {function_return}")
                                    
                                    # Append the function call result to the chat history
                                    messages.append({
                                        "tool_call_id": tool_call["id"],
                                        "role": "tool",
                                        "name": tool_call["function"]["name"],
                                        "content": function_return,
                                    })
                        
                        # Get final response after function call
                        body["messages"] = messages
                        response = requests.post(f"{self.openai_endpoint}/chat/completions", headers=headers, json=body, timeout=self.timeout)
                        
                        if response.status_code == 429:
                            error_data = response.json()
                            wait_seconds = error_data.get("error", {}).get("details", "").split("wait ")[-1].split(" ")[0] if "wait " in error_data.get("error", {}).get("details", "") else "unknown"
                            logger.warning(f"OpenAI rate limit exceeded on second call. Wait {wait_seconds} seconds.")
                            return f"RATE_LIMIT_EXCEEDED:{wait_seconds}"
                        
                        elif response.status_code == 200:
                            response_data = response.json()
                        else:
                            logger.error(f"OpenAI API error on second call: {response.status_code}")
                            return f"OPENAI_ERROR:{response.status_code}"
                
                return response_data["choices"][0]["message"]["content"]
                
            except Exception as e:
                logger.error(f"Error calling OpenAI: {e}")
                return f"OPENAI_ERROR:{str(e)[:100]}"
        
        def sync_grok_call():
            """Synchronous Grok-3 API call as fallback."""
            try:
                # Build context-aware prompt for Grok-3
                context_prompt = self.system_prompt
                if user_id and username and self.memory_manager:
                    user_context = self.memory_manager.get_user_context(user_id)
                    user_history = self.memory_manager.get_user_chat_history(user_id, 2)
                    if user_context:
                        context_prompt += f"\nUser context: {user_context}"
                    if user_history:
                        context_prompt += f"\nRecent chat: {user_history}"
                
                # Prepare messages for Grok-3
                messages = [
                    {"role": "system", "content": context_prompt or "You are a helpful AI assistant with memory capabilities."},
                    {"role": "user", "content": user_message}
                ]
                
                # Make Grok-3 API call (simplified without function calling)
                headers = {
                    "Authorization": f"Bearer {self.grok_api_key}",
                    "Content-Type": "application/json"
                }
                
                body = {
                    "model": self.grok_model,
                    "messages": messages,
                    "temperature": 1.0,
                    "top_p": 1.0
                }
                
                response = requests.post(f"{self.grok_endpoint}/chat/completions", headers=headers, json=body, timeout=self.timeout)
                
                if response.status_code == 429:
                    error_data = response.json()
                    wait_seconds = error_data.get("error", {}).get("details", "").split("wait ")[-1].split(" ")[0] if "wait " in error_data.get("error", {}).get("details", "") else "unknown"
                    logger.warning(f"Grok-3 rate limit exceeded. Wait {wait_seconds} seconds.")
                    return f"RATE_LIMIT_EXCEEDED:{wait_seconds}"
                
                elif response.status_code != 200:
                    logger.error(f"Grok-3 API error: {response.status_code} {response.text}")
                    return f"GROK_ERROR:{response.status_code}"
                
                response_data = response.json()
                return response_data["choices"][0]["message"]["content"]
                
            except Exception as e:
                logger.error(f"Error calling Grok-3: {e}")
                return f"GROK_ERROR:{str(e)[:100]}"
        
        loop = asyncio.get_event_loop()
        
        # Try OpenAI first
        openai_response = await loop.run_in_executor(self.executor, sync_openai_call)
        
        # Check if OpenAI hit rate limit or error
        if openai_response.startswith("RATE_LIMIT_EXCEEDED:"):
            wait_seconds = openai_response.split(":")[1]
            logger.info(f"OpenAI rate limited, trying Grok-3 fallback...")
            
            # Try Grok-3 as fallback
            grok_response = await loop.run_in_executor(self.executor, sync_grok_call)
            
            if grok_response.startswith("RATE_LIMIT_EXCEEDED:"):
                # Both services are rate limited
                wait_seconds_grok = grok_response.split(":")[1]
                return f"🤖 Rate limit reached on both AI services! Please wait {wait_seconds} seconds for OpenAI or {wait_seconds_grok} seconds for Grok-3. (Daily limits: 50 requests each)"
            
            elif grok_response.startswith("GROK_ERROR:"):
                # Grok-3 also failed, use fallback response
                logger.warning(f"Grok-3 also failed: {grok_response}")
                return self.get_fallback_response(user_message)
            
            else:
                # Grok-3 succeeded
                logger.info("Successfully used Grok-3 fallback")
                return f"🤖 [Grok-3] {grok_response}"
        
        elif openai_response.startswith("OPENAI_ERROR:"):
            # OpenAI failed with other error, try Grok-3
            error_msg = openai_response.split(":", 1)[1]
            logger.info(f"OpenAI failed with error: {error_msg}, trying Grok-3 fallback...")
            
            grok_response = await loop.run_in_executor(self.executor, sync_grok_call)
            
            if grok_response.startswith("RATE_LIMIT_EXCEEDED:") or grok_response.startswith("GROK_ERROR:"):
                # Grok-3 also failed, use fallback response
                logger.warning(f"Grok-3 also failed: {grok_response}")
                return self.get_fallback_response(user_message)
            
            else:
                # Grok-3 succeeded
                logger.info("Successfully used Grok-3 fallback after OpenAI error")
                return f"🤖 [Grok-3] {grok_response}"
        
        else:
            # OpenAI succeeded
            return openai_response

    def get_fallback_response(self, user_message: str) -> str:
        """Get a simple fallback response when AI is not available."""
        message_lower = user_message.lower()
        
        # Simple keyword-based responses
        if any(word in message_lower for word in ["hello", "hi", "สวัสดี", "หวัดดี"]):
            return "สวัสดีครับ! 👋"
        elif any(word in message_lower for word in ["how are you", "เป็นไง", "สบายดีไหม"]):
            return "สบายดีครับ! 😊"
        elif any(word in message_lower for word in ["bye", "goodbye", "ลาก่อน", "บ๊ายบาย"]):
            return "ลาก่อนครับ! 👋"
        elif any(word in message_lower for word in ["thanks", "thank you", "ขอบคุณ"]):
            return "ยินดีครับ! 😊"
        elif any(word in message_lower for word in ["help", "ช่วย", "ช่วยเหลือ"]):
            return "ใช้คำสั่ง `!help` เพื่อดูคำสั่งที่มีครับ! 📚"
        elif any(word in message_lower for word in ["weather", "อากาศ", "ฝน"]):
            return "ขออภัยครับ ตอนนี้ไม่สามารถตรวจสอบอากาศได้ 😅"
        elif any(word in message_lower for word in ["time", "เวลา", "กี่โมง"]):
            import datetime
            current_time = datetime.datetime.now().strftime("%H:%M:%S")
            return f"เวลาปัจจุบัน: {current_time} ⏰"
        else:
            fallback_responses = [
                "ขออภัยครับ ตอนนี้ AI ไม่พร้อมใช้งาน 😅",
                "ขออภัยครับ ระบบ AI กำลังปรับปรุง 🛠️",
                "ขออภัยครับ ตอนนี้ไม่สามารถตอบได้ 😔",
                "ขออภัยครับ ระบบ AI กำลังทำงานหนัก 🥵",
                "ขออภัยครับ ตอนนี้ไม่พร้อมตอบ 😴"
            ]
            import random
            return random.choice(fallback_responses)

# --- Helper function to highlight usernames in AI response ---
def highlight_usernames(bot, message: discord.Message, ai_response: str) -> str:
    if not hasattr(message.channel, "guild") or message.channel.guild is None:
        return ai_response

    names = set()
    for member in message.channel.guild.members:
        names.add(member.display_name)
        names.add(member.name)

    for name in sorted(names, key=len, reverse=True):
        if len(name) < 2:
            continue
        pattern = r'\b{}\b'.format(re.escape(name))
        ai_response = re.sub(pattern, f'⭐{name}⭐', ai_response, flags=re.IGNORECASE)
    return ai_response

# --- Discord Bot Class ---
ALLOWED_CHANNEL_IDS = [1385234032765178007]  # Define channels where bot responds

class DiscordBot(commands.Bot):
    def __init__(self, config: Config):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(
            command_prefix=config.command_prefix,
            intents=intents,
            help_command=None
        )
        self.config = config
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
        self.memory_manager = MemoryManager()
        self.ai_service = AIService(executor=self.executor, memory_manager=self.memory_manager)
        self.allowed_channel_ids = ALLOWED_CHANNEL_IDS
        self.username_cache = {}
        self.add_commands()
        self.add_events()
        # DO NOT start the task here, the event loop is not running yet.
        # self.update_username_cache.start()

    def add_events(self):
        @self.event
        async def on_ready():
            logger.info(f'Bot is ready! Logged in as {self.user.name} ({self.user.id})')
            logger.info(f'Connected to {len(self.guilds)} guilds')
            logger.info(f'Allowed channels: {self.allowed_channel_ids}')
            
            # Start background tasks
            self.update_username_cache.start()
            self.save_memories_periodically.start()
            self.disk_space_monitor.start()
            
            # Send startup message to allowed channels
            for channel_id in self.allowed_channel_ids:
                channel = self.get_channel(channel_id)
                if channel:
                    try:
                        # Get disk usage info
                        bot_usage = get_disk_usage()
                        
                        embed = discord.Embed(
                            title="🤖 Bot Started Successfully!",
                            description="AI bot is now online and ready to chat!",
                            color=0x00ff00,
                            timestamp=datetime.datetime.now(datetime.UTC)
                        )
                        embed.add_field(name="Memory System", value="✅ Active", inline=True)
                        embed.add_field(name="URL Analysis", value="✅ Active", inline=True)
                        embed.add_field(name="AI Chat", value="✅ OpenAI + Grok-3 Fallback", inline=True)
                        embed.add_field(name="💾 Bot Files", value=f"{bot_usage:.2f} MB", inline=True)
                        embed.add_field(name="🤖 AI Provider", value="OpenAI with Grok-3 Fallback", inline=True)
                        embed.add_field(name="🔄 Auto Cleanup", value="✅ Active", inline=True)
                        
                        await channel.send(embed=embed)
                    except Exception as e:
                        logger.error(f"Failed to send startup message to channel {channel_id}: {e}")

        @self.event
        async def on_message(message):
            if message.author == self.user:
                return
            
            # Check if message is a command (starts with command prefix)
            if message.content.startswith(self.config.command_prefix):
                # Process commands only, don't generate AI response
                await self.process_commands(message)
                return
            
            # Handle chat messages (non-commands)
            await self.handle_chat_message(message)

        @self.event
        async def on_command_error(ctx, error):
            if isinstance(error, commands.CommandNotFound):
                await ctx.send("คำสั่งไม่ถูกต้อง! ใช้ `!help` ดูคำสั่งที่มี")
            elif isinstance(error, commands.MissingRequiredArgument):
                await ctx.send("ใส่ข้อมูลไม่ครบ! ดูตัวอย่างการใช้งาน")
            elif isinstance(error, commands.CheckFailure):
                await ctx.send("🚫 คุณไม่มีสิทธิ์ใช้คำสั่งนี้ (Owner only).")
            else:
                logger.error(f"Command error: {error}")
                await ctx.send("เกิดข้อผิดพลาดในคำสั่ง!")

    def add_commands(self):
        @self.command(name='test', aliases=['ping', 'pong'])
        async def test_command(ctx):
            """Simple test command to check if bot is working."""
            await ctx.send(f"✅ Bot is working! Pong! 🏓")

        @self.command(name='hello', aliases=['hi', 'สวัสดี'])
        async def hello(ctx):
            highlighted_name = f' |`{ctx.author.display_name}`| '
            await ctx.send(f'Hello {highlighted_name} นะไอ้โง่!')

        @self.command(name='help', aliases=['h'])
        async def help_command(ctx):
            embed = discord.Embed(
                title="📚 คำสั่งที่มีในบอท",
                description="รวมคำสั่งทั้งหมดของบอทนี้",
                color=0x00ff00
            )
            # General commands
            embed.add_field(name=f"{self.config.command_prefix}hello", value="ทักทายบอท", inline=False)
            embed.add_field(name=f"{self.config.command_prefix}help", value="แสดงข้อความช่วยเหลือนี้", inline=False)
            embed.add_field(name=f"{self.config.command_prefix}status", value="แสดงสถานะของบอทและระบบ", inline=False)
            embed.add_field(name="การแชทกับ AI", value="พิมพ์ข้อความธรรมดาในห้องที่กำหนดเพื่อคุยกับ AI (OpenAI + Grok-3 Fallback)", inline=False)
            embed.add_field(name="🔄 Reply to Messages", value="กด Reply บนข้อความเพื่อให้บอทตอบกลับข้อความนั้นโดยตรง", inline=False)
            embed.add_field(name="🌐 URL Analysis", value="บอทจะอ่านและวิเคราะห์เว็บไซต์อัตโนมัติเมื่อพบ URL ในข้อความ", inline=False)
            
            # Memory commands
            embed.add_field(name="\u200b", value="--- 🧠 **Memory Commands** ---", inline=False)
            embed.add_field(name=f"{self.config.command_prefix}profile [@user]", value="ดูข้อมูลและบุคลิกภาพของผู้ใช้", inline=False)
            embed.add_field(name=f"{self.config.command_prefix}memory", value="ดูสถิติความจำของบอท", inline=False)
            embed.add_field(name=f"{self.config.command_prefix}thread [message_id]", value="ดูการสนทนาล่าสุดหรือ thread เฉพาะ", inline=False)
            embed.add_field(name=f"{self.config.command_prefix}forget [@user]", value="ลบข้อมูลของผู้ใช้จากความจำ (Owner only)", inline=False)
            
            # Separator for Admin commands
            embed.add_field(name="\u200b", value="--- 🔒 **Admin Commands (Owner only)** ---", inline=False)

            # Admin commands (Owner only)
            embed.add_field(name=f"{self.config.command_prefix}setprompt [ข้อความ]", value="ตั้งค่า AI system prompt ใหม่ (เปลี่ยนบุคลิก AI)", inline=False)
            embed.add_field(name=f"{self.config.command_prefix}ai", value="แสดงสถานะ AI provider", inline=False)
            embed.add_field(name=f"{self.config.command_prefix}restart", value="รีสตาร์ทบอท", inline=False)
            embed.add_field(name=f"{self.config.command_prefix}terminal [command]", value="รันคำสั่ง shell บนเครื่องที่บอททำงานอยู่", inline=False)
            embed.add_field(name=f"{self.config.command_prefix}diagnose", value="ให้ AI วิเคราะห์ข้อผิดพลาดจาก `bot.log`", inline=False)
            embed.add_field(name=f"{self.config.command_prefix}diskspace", value="ตรวจสอบการใช้พื้นที่ดิสก์", inline=False)
            embed.add_field(name=f"{self.config.command_prefix}cleanup", value="ลบไฟล์เก่าเพื่อประหยัดพื้นที่ดิสก์ (Owner only)", inline=False)
            embed.add_field(name=f"{self.config.command_prefix}clearcache", value="ลบ HuggingFace AI cache (Owner only)", inline=False)
            embed.add_field(name=f"{self.config.command_prefix}activity", value="ดูสถานะการทำงานของบอท (Owner only)", inline=False)
            embed.add_field(name=f"{self.config.command_prefix}debug", value="ดู debug ข้อมูลบอท (Owner only)", inline=False)
            
            # URL Analysis commands
            embed.add_field(name="\u200b", value="--- 🌐 **URL Analysis Commands** ---", inline=False)
            embed.add_field(name=f"{self.config.command_prefix}analyze [URL]", value="วิเคราะห์เว็บไซต์จาก URL ที่กำหนด", inline=False)
            
            embed.add_field(name="\u200b", value="\n**หมายเหตุ:** คำสั่งในหมวด Admin ใช้ได้เฉพาะ Owner เท่านั้น!", inline=False)
            
            await ctx.send(embed=embed)

        @self.command(name='reply', aliases=['r', 'ตอบกลับ'])
        async def reply_help(ctx):
            """Show how to use the reply feature."""
            embed = discord.Embed(
                title="🔄 How to Reply to Messages",
                description="เรียนรู้วิธีให้บอทตอบกลับข้อความเฉพาะ",
                color=0x00ff00
            )
            
            embed.add_field(
                name="📱 วิธีใช้",
                value="1. กดปุ่ม **Reply** บนข้อความที่ต้องการตอบกลับ\n"
                      "2. พิมพ์ข้อความของคุณ\n"
                      "3. บอทจะตอบกลับข้อความนั้นโดยตรง",
                inline=False
            )
            
            embed.add_field(
                name="💡 ตัวอย่าง",
                value="**ข้อความเดิม:** 'ใครรู้จัก Python ไหม?'\n"
                      "**คุณ Reply:** 'ผมรู้จักครับ มันเป็นภาษาโปรแกรมมิ่ง'\n"
                      "**บอทจะตอบ:** [ตอบกลับข้อความเดิมพร้อมคำอธิบายเพิ่มเติม]",
                inline=False
            )
            
            embed.add_field(
                name="🎯 ประโยชน์",
                value="• ตอบคำถามได้ตรงประเด็น\n"
                      "• ต่อยอดจากข้อความเดิม\n"
                      "• สร้างบทสนทนาที่ต่อเนื่อง\n"
                      "• จำบริบทได้ดีขึ้น",
                inline=False
            )
            
            embed.add_field(
                name="⚠️ หมายเหตุ",
                value="• ต้องใช้ในห้องที่บอททำงานอยู่\n"
                      "• บอทจะจำข้อความที่ตอบกลับ\n"
                      "• สามารถตอบกลับข้อความของตัวเองได้",
                inline=False
            )
            
            await ctx.send(embed=embed)

        @self.command(name='profile', aliases=['user', 'personality'])
        async def profile(ctx, user: discord.Member = None):
            """Show user profile and personality data."""
            if user is None:
                user = ctx.author
            
            user_id = str(user.id)
            if user_id not in self.memory_manager.user_personalities:
                await ctx.send(f"❌ ไม่มีข้อมูลของ {user.display_name} ในความจำของบอท")
                return
            
            user_data = self.memory_manager.user_personalities[user_id]
            
            embed = discord.Embed(
                title=f"🧠 Profile: {user.display_name}",
                color=0x00ff00,
                timestamp=datetime.datetime.utcnow()
            )
            
            embed.add_field(name="📊 Messages", value=str(user_data["message_count"]), inline=True)
            embed.add_field(name="👋 First Seen", value=user_data["first_seen"][:10], inline=True)
            embed.add_field(name="🕒 Last Active", value=user_data["last_interaction"][:10], inline=True)
            
            if user_data["personality_traits"]:
                traits = ", ".join(user_data["personality_traits"])
                embed.add_field(name="🎭 Personality", value=traits, inline=False)
            
            if user_data["topics"]:
                top_topics = sorted(user_data["topics"].items(), key=lambda x: x[1], reverse=True)[:5]
                topics_text = "\n".join([f"• {topic}: {count} times" for topic, count in top_topics])
                embed.add_field(name="🎯 Interests", value=topics_text, inline=False)
            
            await ctx.send(embed=embed)

        @self.command(name='memory', aliases=['mem', 'stats'])
        async def memory_stats(ctx):
            """Show bot memory statistics."""
            total_users = len(self.memory_manager.user_personalities)
            total_chats = len(self.memory_manager.chat_history)
            
            embed = discord.Embed(
                title="🧠 Bot Memory Statistics",
                color=0x00ff00,
                timestamp=datetime.datetime.utcnow()
            )
            
            embed.add_field(name="👥 Users Remembered", value=str(total_users), inline=True)
            embed.add_field(name="💬 Chat Entries", value=str(total_chats), inline=True)
            embed.add_field(name="📁 Memory Files", value="brain_chat_memory.txt, user_personalities.json", inline=False)
            
            if total_users > 0:
                most_active = max(self.memory_manager.user_personalities.items(), 
                                key=lambda x: x[1]["message_count"])
                embed.add_field(name="🏆 Most Active User", 
                              value=f"{most_active[1]['username']} ({most_active[1]['message_count']} messages)", 
                              inline=False)
            
            await ctx.send(embed=embed)

        @self.command(name='thread', aliases=['t', 'conversation'])
        async def view_thread(ctx, message_id: str = None):
            """View conversation thread around a message."""
            if not message_id:
                # If no message ID provided, show recent conversations
                recent_chats = self.memory_manager.get_recent_chat_context(5)
                if recent_chats:
                    embed = discord.Embed(
                        title="💬 Recent Conversations",
                        description=f"```\n{recent_chats}\n```",
                        color=0x00ff00
                    )
                    embed.add_field(
                        name="💡 Tip", 
                        value="Use `!thread <message_id>` to view specific conversation thread",
                        inline=False
                    )
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("❌ ไม่มีข้อมูลการสนทนาล่าสุด")
                return
            
            # Get conversation thread for specific message
            thread = self.memory_manager.get_conversation_thread(message_id, 10)
            if thread:
                thread_text = "\n".join(thread)
                embed = discord.Embed(
                    title=f"🧵 Conversation Thread (ID: {message_id})",
                    description=f"```\n{thread_text}\n```",
                    color=0x00ff00
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send(f"❌ ไม่พบการสนทนาที่เกี่ยวข้องกับ ID: {message_id}")

        @self.command(name='forget')
        @commands.check(is_owner)
        async def forget_user(ctx, user: discord.Member):
            """Remove user data from bot memory (Owner only)."""
            user_id = str(user.id)
            if user_id in self.memory_manager.user_personalities:
                del self.memory_manager.user_personalities[user_id]
                self.memory_manager.save_memories()
                await ctx.send(f"✅ ลบข้อมูลของ {user.display_name} ออกจากความจำแล้ว")
            else:
                await ctx.send(f"❌ ไม่พบข้อมูลของ {user.display_name} ในความจำ")

        @self.command(name='setprompt')
        @commands.check(is_owner)
        async def setprompt(ctx, *, prompt: str):
            self.ai_service.set_system_prompt(prompt)
            await ctx.send(f"ตั้งค่า AI system prompt ใหม่เรียบร้อย:\n```{prompt}```")

        @self.command(name='ai', aliases=['provider', 'model'])
        async def ai_status(ctx):
            """Show current AI provider status."""
            embed = discord.Embed(
                title="🤖 AI Provider Status",
                color=0x00ff00,
                timestamp=datetime.datetime.now(datetime.UTC)
            )
            
            # Current provider
            embed.add_field(name="Primary Provider", value="🔄 OpenAI", inline=True)
            embed.add_field(name="Fallback Provider", value="🦘 Grok-3", inline=True)
            
            # OpenAI status
            openai_status = "✅ Available" if self.ai_service.openai_api_key else "❌ Not Available"
            embed.add_field(name="OpenAI Status", value=openai_status, inline=True)
            
            # Grok-3 status
            grok_status = "✅ Available" if self.ai_service.grok_api_key else "❌ Not Available"
            embed.add_field(name="Grok-3 Status", value=grok_status, inline=True)
            
            # Model info
            embed.add_field(name="OpenAI Model", value=self.ai_service.openai_model, inline=True)
            embed.add_field(name="Grok-3 Model", value=self.ai_service.grok_model, inline=True)
            
            # Function calling info
            embed.add_field(name="Function Calling", value="✅ Available (OpenAI only)", inline=True)
            embed.add_field(name="Available Functions", value="getFlightInfo", inline=True)
            
            # Usage instructions
            embed.add_field(
                name="💡 AI Service", 
                value="Using OpenAI with Grok-3 fallback. When OpenAI hits rate limits, Grok-3 will be used automatically.", 
                inline=False
            )
            
            embed.add_field(
                name="🔄 Fallback Logic", 
                value="1. Try OpenAI first\n2. If rate limited → Use Grok-3\n3. If both fail → Use fallback responses", 
                inline=False
            )
            
            await ctx.send(embed=embed)

        @self.command(name='debug')
        @commands.check(is_owner)
        async def debug(ctx):
            """Check bot and AI service status."""
            try:
                embed = discord.Embed(
                    title="🔧 Debug Information",
                    color=0x00ff00,
                    timestamp=datetime.datetime.now(datetime.UTC)
                )
                
                # AI Provider status
                embed.add_field(name="Primary Provider", value="OpenAI", inline=True)
                embed.add_field(name="Fallback Provider", value="Grok-3", inline=True)
                embed.add_field(name="OpenAI Status", value="✅" if self.ai_service.openai_api_key else "❌", inline=True)
                embed.add_field(name="Grok-3 Status", value="✅" if self.ai_service.grok_api_key else "❌", inline=True)
                embed.add_field(name="OpenAI API Key", value="✅" if self.ai_service.openai_api_key else "❌", inline=True)
                embed.add_field(name="Grok-3 API Key", value="✅" if self.ai_service.grok_api_key else "❌", inline=True)
                embed.add_field(name="OpenAI Endpoint", value=self.ai_service.openai_endpoint, inline=True)
                embed.add_field(name="Grok-3 Endpoint", value=self.ai_service.grok_endpoint, inline=True)
                embed.add_field(name="OpenAI Model", value=self.ai_service.openai_model, inline=True)
                embed.add_field(name="Grok-3 Model", value=self.ai_service.grok_model, inline=True)
                embed.add_field(name="Function Calling", value="✅" if self.ai_service.function_schemas else "❌", inline=True)
                
                # Test AI response
                await ctx.send("Testing AI service...")
                response = await self.ai_service.get_response("Say 'pong' if you are working.")
                embed.add_field(name="AI Test Response", value=response[:100] + "..." if len(response) > 100 else response, inline=False)
                
                await ctx.send(embed=embed)
            except Exception as e:
                await ctx.send(f"AI service error: {e}")

        @self.command(name='status')
        async def status(ctx):
            import platform
            import psutil
            import datetime

            # Bot stats
            latency = round(self.latency * 1000)
            servers = len(self.guilds)
            users = len(self.users)
            channels = sum(1 for _ in self.get_all_channels())
            commands_count = len(self.commands)
            allowed_channels = ', '.join(str(cid) for cid in self.allowed_channel_ids)

            # System stats
            cpu_percent = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            mem_used = f"{mem.used // (1024**2)} MB"
            mem_total = f"{mem.total // (1024**2)} MB"
            mem_percent = mem.percent
            boot_time = datetime.datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
            python_version = platform.python_version()
            os_info = f"{platform.system()} {platform.release()} ({platform.version()})"
            process = psutil.Process(os.getpid())
            uptime = datetime.datetime.now() - datetime.datetime.fromtimestamp(process.create_time())
            uptime_str = str(uptime).split('.')[0]

            embed = discord.Embed(
                title="📊 Bot & System Status",
                color=0x0099ff,
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="Latency", value=f"{latency} ms", inline=True)
            embed.add_field(name="Servers", value=str(servers), inline=True)
            embed.add_field(name="Users", value=str(users), inline=True)
            embed.add_field(name="Channels", value=str(channels), inline=True)
            embed.add_field(name="Commands", value=str(commands_count), inline=True)
            embed.add_field(name="Allowed Channel IDs", value=allowed_channels, inline=False)
            embed.add_field(name="Uptime", value=uptime_str, inline=True)
            embed.add_field(name="Python", value=python_version, inline=True)
            embed.add_field(name="OS", value=os_info, inline=False)
            embed.add_field(name="CPU Usage", value=f"{cpu_percent}%", inline=True)
            embed.add_field(name="Memory Usage", value=f"{mem_used} / {mem_total} ({mem_percent}%)", inline=True)
            embed.add_field(name="System Boot Time", value=boot_time, inline=False)
            await ctx.send(embed=embed)

        @self.command(name='restart')
        @commands.check(is_owner)
        async def restart(ctx):
            """Restarts the bot cleanly."""
            await ctx.send("✅ กำลังรีสตาร์ท...")
            await asyncio.sleep(1)  # Ensures the message is sent before shutdown
            
            # Save memories before restart
            self.memory_manager.save_memories()
            
            # Stop background tasks
            self.update_username_cache.cancel()
            self.save_memories_periodically.cancel()
            self.disk_space_monitor.cancel()
            
            # Close the bot gracefully
            await self.close()
            
            # Start new process
            try:
                subprocess.Popen([sys.executable] + sys.argv)
                # Exit the current process
                os._exit(0)  # Use os._exit instead of sys.exit to avoid SystemExit exception
            except Exception as e:
                logger.error(f"Error during restart: {e}")
                await ctx.send(f"❌ Error during restart: {e}")

        @self.command(name='activity')
        @commands.check(is_owner)
        async def activity(ctx):
            process = psutil.Process(os.getpid())
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            uptime = datetime.datetime.now() - datetime.datetime.fromtimestamp(process.create_time())
            uptime_str = str(uptime).split('.')[0]
            embed = discord.Embed(
                title="🤖 Bot Activity",
                color=0x00bfff,
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="Uptime", value=uptime_str, inline=True)
            embed.add_field(name="CPU Usage", value=f"{cpu}%", inline=True)
            embed.add_field(name="Memory Usage", value=f"{mem.percent}%", inline=True)
            embed.add_field(name="Current PID", value=str(process.pid), inline=True)
            embed.add_field(name="Status", value=process.status(), inline=True)
            embed.add_field(name="Threads", value=str(process.num_threads()), inline=True)
            embed.add_field(name="Executable", value=process.exe(), inline=False)
            await ctx.send(embed=embed)

        @self.command(name='terminal', aliases=['term', 'cmd'])
        @commands.check(is_owner)
        async def terminal(ctx, *, command: str):
            """Executes a shell command. Admin only."""
            async with ctx.typing():
                try:
                    proc = await asyncio.create_subprocess_shell(
                        command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)
                    result = ""
                    if stdout:
                        result += f"**Output:**\n```\n{stdout.decode('utf-8', errors='ignore')}\n```\n"
                    if stderr:
                        result += f"**Error:**\n```\n{stderr.decode('utf-8', errors='ignore')}\n```"
                    if not result:
                        result = "Command executed with no output."
                    if len(result) > 2000:
                        with open("terminal_output.txt", "w", encoding="utf-8") as f:
                            f.write(stdout.decode('utf-8', errors='ignore'))
                            f.write("\n\n---ERRORS---\n\n")
                            f.write(stderr.decode('utf-8', errors='ignore'))
                        await ctx.send("Output is too long. Sending as a file.", file=discord.File("terminal_output.txt"))
                        os.remove("terminal_output.txt")
                    else:
                        await ctx.send(result)
                except asyncio.TimeoutError:
                    await ctx.send("Command timed out after 60 seconds.")
                except Exception as e:
                    await ctx.send(f"An error occurred: {e}")

        @self.command(name='diagnose')
        @commands.check(is_owner)
        async def diagnose(ctx):
            """Diagnose bot issues using AI."""
            try:
                # Get system information
                cpu_percent = psutil.cpu_percent()
                memory = psutil.virtual_memory()
                disk_usage = get_disk_usage()
                
                # Read recent log entries
                log_entries = []
                try:
                    with open('logs/bot.log', 'r', encoding='utf-8') as f:
                        log_entries = f.readlines()[-20:]  # Last 20 lines
                except:
                    pass
                
                # Create diagnosis prompt
                diagnosis_prompt = f"""
                System Status:
                - CPU Usage: {cpu_percent}%
                - Memory Usage: {memory.percent}%
                - Disk Usage: {disk_usage:.2f} MB
                
                Recent Log Entries:
                {''.join(log_entries)}
                
                Please analyze the bot's health and provide recommendations for any issues.
                """
                
                # Get AI diagnosis using the async method
                response = await self.ai_service.get_response(diagnosis_prompt)
                
                # Create embed
                embed = discord.Embed(
                    title="🤖 Bot Diagnosis",
                    description=response[:2000],
                    color=0x00ff00
                )
                embed.add_field(name="System Info", value=f"CPU: {cpu_percent}% | RAM: {memory.percent}% | Disk: {disk_usage:.2f}MB", inline=False)
                
                await ctx.send(embed=embed)
                
            except Exception as e:
                await ctx.send(f"❌ Diagnosis failed: {str(e)}")

        @self.command(name='diskspace', aliases=['disk', 'space'])
        async def disk_usage(ctx):
            """Check disk usage for bot files and AI models."""
            if not await is_admin(ctx):
                await ctx.send("❌ This command is admin-only.")
                return
            
            try:
                bot_usage = get_disk_usage()
                hf_cache_size = get_directory_size("hf_cache") if os.path.exists("hf_cache") else 0
                total_usage = bot_usage + hf_cache_size
                
                embed = discord.Embed(
                    title="💾 Disk Usage Report",
                    color=0x00ff00,
                    timestamp=datetime.datetime.now(datetime.UTC)
                )
                embed.add_field(name="Bot Files", value=f"{bot_usage:.2f} MB", inline=True)
                embed.add_field(name="AI Models Cache", value=f"{hf_cache_size:.2f} MB", inline=True)
                embed.add_field(name="Total Usage", value=f"{total_usage:.2f} MB", inline=True)
                
                # Add status indicators
                bot_status = "🟢 Normal" if bot_usage < 500 else "🟡 High" if bot_usage < 1000 else "🔴 Critical"
                hf_status = "🟢 Normal" if hf_cache_size < 2000 else "🟡 Large" if hf_cache_size < 5000 else "🔴 Critical"
                
                embed.add_field(name="Bot Files Status", value=bot_status, inline=True)
                embed.add_field(name="AI Cache Status", value=hf_status, inline=True)
                embed.add_field(name="Auto Cleanup", value="✅ Active", inline=True)
                
                await ctx.send(embed=embed)
                
            except Exception as e:
                logger.error(f"Error in disk usage command: {e}")
                await ctx.send(f"❌ Error checking disk usage: {e}")

        @self.command(name='clearcache', aliases=['clearhf', 'cleanai'])
        async def clear_hf_cache(ctx):
            """Clear HuggingFace model cache to free up space."""
            if not await is_admin(ctx):
                await ctx.send("❌ This command is admin-only.")
                return
            
            try:
                hf_cache_path = "hf_cache"
                if os.path.exists(hf_cache_path):
                    import shutil
                    shutil.rmtree(hf_cache_path)
                    os.makedirs(hf_cache_path)  # Recreate empty directory
                    
                    embed = discord.Embed(
                        title="🧹 AI Cache Cleared",
                        description="HuggingFace model cache has been cleared successfully!",
                        color=0x00ff00,
                        timestamp=datetime.datetime.now(datetime.UTC)
                    )
                    embed.add_field(name="Next Model Load", value="Will download fresh models", inline=True)
                    embed.add_field(name="Space Freed", value="AI models will be re-downloaded when needed", inline=True)
                    
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("ℹ️ No HuggingFace cache found to clear.")
                    
            except Exception as e:
                logger.error(f"Error clearing HuggingFace cache: {e}")
                await ctx.send(f"❌ Error clearing cache: {e}")

        @self.command(name='analyze', aliases=['url', 'read'])
        async def analyze_url(ctx, url: str):
            """Analyze a website or platform URL."""
            if not is_valid_url(url):
                await ctx.send("❌ URL ไม่ถูกต้อง กรุณาใส่ URL ที่ถูกต้อง")
                return
            
            async with ctx.typing():
                try:
                    await ctx.send(f"🔍 กำลังอ่านและวิเคราะห์: {url}")
                    
                    # Use the new platform-aware analyzer
                    content = await analyze_any_url(self, url)
                    
                    if content.startswith("Error") or content.startswith("❌"):
                        await ctx.send(f"❌ ไม่สามารถอ่านหรือวิเคราะห์ได้: {content}")
                        return
                    
                    # Ask AI to provide a comprehensive summary
                    platform = detect_platform(url)
                    if platform == 'website':
                        prompt = f"""
                        วิเคราะห์เนื้อหาจากเว็บไซต์นี้และสรุปให้เข้าใจง่าย:

                        URL: {url}
                        เนื้อหา:
                        {content}

                        กรุณาให้สรุปที่ครอบคลุมและเข้าใจง่าย:
                        1. **หัวข้อหลัก** - สรุปหัวข้อสำคัญ
                        2. **ประเด็นสำคัญ** - จุดสำคัญที่ควรรู้ (3-5 ข้อ)
                        3. **ข้อมูลเพิ่มเติม** - ข้อมูลที่น่าสนใจอื่นๆ
                        4. **สรุปโดยรวม** - ความคิดเห็นหรือข้อสังเกต

                        ใช้ภาษาไทยที่เข้าใจง่ายและกระชับ
                        """
                    else:
                        prompt = f"""
                        วิเคราะห์เนื้อหาจาก {platform} และสรุปให้เข้าใจง่าย:

                        URL: {url}
                        ข้อมูล:
                        {content}

                        กรุณาให้สรุปที่ครอบคลุมและเข้าใจง่าย:
                        1. **ข้อมูลหลัก** - สรุปข้อมูลสำคัญ
                        2. **ประเด็นที่น่าสนใจ** - จุดเด่นหรือข้อมูลที่น่าสนใจ
                        3. **สรุปโดยรวม** - ความคิดเห็นหรือข้อสังเกต

                        ใช้ภาษาไทยที่เข้าใจง่ายและกระชับ
                        """
                    
                    ai_summary = await self.ai_service.get_response(prompt)
                    
                    embed = discord.Embed(
                        title=f"🌐 การวิเคราะห์: {url}",
                        description=ai_summary[:4000],
                        color=0x00ff00,
                        url=url
                    )
                    embed.add_field(name="📊 แพลตฟอร์ม", value=platform.upper(), inline=True)
                    embed.add_field(name="⏰ เวลาวิเคราะห์", value=datetime.datetime.now().strftime("%H:%M:%S"), inline=True)
                    
                    await ctx.send(embed=embed)
                    
                except Exception as e:
                    logger.error(f"Error in analyze command: {e}", exc_info=True)
                    await ctx.send(f"❌ เกิดข้อผิดพลาดที่ไม่คาดคิดในการวิเคราะห์: {e}")

        @self.command(name='cleanup', aliases=['clean'])
        async def cleanup_files(ctx):
            """Clean up old files and optionally AI cache to save disk space."""
            if not await is_admin(ctx):
                await ctx.send("❌ This command is admin-only.")
                return
            
            try:
                # Clean bot files
                cleanup_old_files()
                self.memory_manager._cleanup_memories()
                
                # Clear old log files
                if os.path.exists('logs'):
                    log_files = [f for f in os.listdir('logs') if f.startswith('bot.log')]
                    if len(log_files) > 3:
                        log_files.sort()
                        for old_log in log_files[:-3]:
                            try:
                                os.remove(os.path.join('logs', old_log))
                            except:
                                pass
                
                bot_usage_after = get_disk_usage()
                hf_cache_size = get_directory_size("hf_cache") if os.path.exists("hf_cache") else 0
                
                embed = discord.Embed(
                    title="🧹 Cleanup Completed",
                    description="Old files and memory have been cleaned up!",
                    color=0x00ff00,
                    timestamp=datetime.datetime.now(datetime.UTC)
                )
                embed.add_field(name="Bot Files Usage", value=f"{bot_usage_after:.2f} MB", inline=True)
                embed.add_field(name="AI Cache Size", value=f"{hf_cache_size:.2f} MB", inline=True)
                
                if hf_cache_size > 2000:
                    embed.add_field(
                        name="💡 Suggestion", 
                        value="AI cache is large. Use `!clearcache` to free more space.", 
                        inline=False
                    )
                
                await ctx.send(embed=embed)
                
            except Exception as e:
                logger.error(f"Error in cleanup command: {e}")
                await ctx.send(f"❌ Cleanup failed: {e}")

    @tasks.loop(hours=1)
    async def update_username_cache(self):
        """Update username cache periodically."""
        try:
            self.username_cache.clear()
            for guild in self.guilds:
                for member in guild.members:
                    self.username_cache[member.id] = member.display_name
            logger.info(f"Updated username cache with {len(self.username_cache)} users")
        except Exception as e:
            logger.error(f"Error updating username cache: {e}")

    @tasks.loop(minutes=30)
    async def save_memories_periodically(self):
        """Save memories periodically and check disk space."""
        try:
            self.memory_manager.save_memories()
            
            # Check bot directory size only (no more HuggingFace cache)
            bot_usage = get_disk_usage()
            
            if bot_usage > 500:  # If bot files using more than 500MB
                logger.warning(f"Bot directory usage is high: {bot_usage:.2f} MB")
                cleanup_old_files()
                self.memory_manager._cleanup_memories()
                logger.info("Performed automatic cleanup due to high bot directory usage")
            
        except Exception as e:
            logger.error(f"Error in periodic memory save: {e}")

    @tasks.loop(hours=6)
    async def disk_space_monitor(self):
        """Monitor disk space usage and log warnings."""
        try:
            bot_usage = get_disk_usage()
            
            if bot_usage > 1000:
                logger.warning(f"Bot directory usage is very high: {bot_usage:.2f} MB")
                cleanup_old_files()
                self.memory_manager._cleanup_memories()
            elif bot_usage > 500:
                logger.warning(f"Bot directory usage is high: {bot_usage:.2f} MB")
                
        except Exception as e:
            logger.error(f"Error in disk space monitoring: {e}")

    @update_username_cache.before_loop
    async def before_update_username_cache(self):
        await self.wait_until_ready()

    @save_memories_periodically.before_loop
    async def before_save_memories_periodically(self):
        await self.wait_until_ready()

    @disk_space_monitor.before_loop
    async def before_disk_space_monitor(self):
        await self.wait_until_ready()

    async def handle_chat_message(self, message: discord.Message):
        # Add guild check to prevent processing DMs and causing errors
        if not message.guild or message.channel.id not in self.allowed_channel_ids or not message.content.strip():
            logger.debug(f"Message ignored: guild={bool(message.guild)}, channel={message.channel.id if message.guild else 'DM'}, content='{message.content[:50]}...'")
            return
            
        # Skip messages containing ignore keywords
        lowered = message.content.lower()
        if any(word in lowered for word in IGNORE_KEYWORDS):
            return
        
        # Check if owner is mentioned - respond defensively
        if is_owner_mentioned(message.content):
            defensive_responses = [
                f"🤬 ไอ้ {message.author.display_name} อย่ามายุ่งกับ Owner ของฉัน!",
                f"😤 {message.author.display_name} อย่าพูดถึง Owner ของฉัน!",
                f"🤯 ไอ้ {message.author.display_name} อย่ามาแตะต้อง Owner ของฉัน!",
                f"😡 {message.author.display_name} อย่ามายุ่งกับ Owner ของฉัน!",
                f"🤬 ไอ้ {message.author.display_name} อย่าพูดถึง Owner ของฉัน!",
                f"😤 {message.author.display_name} อย่ามาแตะต้อง Owner ของฉัน!",
                f"🤯 ไอ้ {message.author.display_name} อย่ามายุ่งกับ Owner ของฉัน!",
                f"😡 {message.author.display_name} อย่าพูดถึง Owner ของฉัน!"
            ]
            import random
            response = random.choice(defensive_responses)
            await message.channel.send(response)
            return
        
        # Check for message replies
        replied_message = None
        if message.reference and message.reference.message_id:
            try:
                replied_message = await message.channel.fetch_message(message.reference.message_id)
            except discord.NotFound:
                await message.channel.send("❌ ไม่พบข้อความที่อ้างถึง")
                return
            except Exception as e:
                logger.error(f"Error fetching replied message: {e}")
        
        # Check for URLs in the message
        urls = extract_urls(message.content)
        
        async with message.channel.typing():
            try:
                # If URLs are found, analyze them first
                if urls:
                    for url in urls[:2]:  # Limit to first 2 URLs
                        try:
                            await message.channel.send(f"🔍 พบ URL ในข้อความ กำลังวิเคราะห์: {url}")
                            content = await analyze_any_url(self, url)
                            
                            if not content.startswith("Error") and not content.startswith("❌"):
                                # Ask AI for a brief summary
                                platform = detect_platform(url)
                                prompt = f"""
                                วิเคราะห์เนื้อหาจาก {platform} และสรุปสั้นๆ ให้เข้าใจง่าย:

                                URL: {url}
                                ข้อมูล:
                                {content[:2000]}

                                กรุณาให้สรุปสั้นๆ (2-3 ประโยค) เกี่ยวกับเนื้อหาหลักและประเด็นสำคัญ
                                ใช้ภาษาไทยที่เข้าใจง่าย
                                """
                                
                                ai_summary = await self.ai_service.get_response(prompt)
                                await message.channel.send(f"📄 **สรุป:** {ai_summary}")
                        except Exception as e:
                            await message.channel.send(f"❌ ไม่สามารถวิเคราะห์ URL ได้: {e}")
                
                # Process the original message with AI (now with memory and reply context)
                image_urls = []
                for attachment in message.attachments:
                    if attachment.content_type and attachment.content_type.startswith("image"):
                        image_urls.append(attachment.url)
                
                # Build context-aware prompt
                user_message = message.content
                if replied_message:
                    # Add reply context to the message
                    reply_context = f"[Replying to {replied_message.author.display_name}: {replied_message.content}] "
                    user_message = reply_context + user_message
                    
                    # Also save the replied message to memory for context
                    self.memory_manager.add_chat_memory(
                        str(replied_message.author.id),
                        replied_message.author.display_name,
                        replied_message.content,
                        "[Message was replied to]",
                        str(replied_message.id)
                    )
                
                # Get AI response with user context and reply context
                response = await self.ai_service.get_response(
                    user_message, 
                    user_id=str(message.author.id),
                    username=message.author.display_name,
                    image_urls=image_urls
                )
                
                # Check if response indicates rate limit or error
                if "Rate limit reached" in response or "OpenAI API error" in response:
                    # Use fallback response instead
                    response = self.ai_service.get_fallback_response(message.content)
                    logger.info(f"Using fallback response due to rate limit/error: {response}")
                
                # Save to memory (only if it's a real AI response, not fallback)
                if "Rate limit reached" not in response and "OpenAI API error" not in response:
                    self.memory_manager.add_chat_memory(
                        str(message.author.id),
                        message.author.display_name,
                        message.content,
                        response,
                        str(replied_message.id) if replied_message else None
                    )
                    self.memory_manager.update_user_personality(
                        str(message.author.id),
                        message.author.display_name,
                        message.content,
                        response
                    )
                
                # Send response as a reply if it was a reply
                mention = message.author.mention
                response = f"{mention} {response}"
                response = highlight_usernames(self, message, response)
                
                if replied_message:
                    # Send as a reply to the original message
                    for chunk in [response[i:i+2000] for i in range(0, len(response), 2000)]:
                        await message.channel.send(chunk, reference=replied_message)
                else:
                    # Send as normal message
                    for chunk in [response[i:i+2000] for i in range(0, len(response), 2000)]:
                        await message.channel.send(chunk)
                    
            except Exception as e:
                logger.error(f"Error processing message: {e}", exc_info=True)
                await message.channel.send(ResponseTemplates.ERROR_MESSAGES["general_error"])

    async def close(self):
        # Notify all allowed channels about shutdown
        for channel_id in self.allowed_channel_ids:
            channel = self.get_channel(channel_id)
            if channel:
                try:
                    await channel.send("⚠️ AI กำลังปิดตัวลง (shutting down)...")
                except Exception as e:
                    logger.error(f"Failed to send shutdown message to channel {channel_id}: {e}")
        
        # Save memories before shutting down
        self.memory_manager.save_memories()
        
        # Stop background tasks and shutdown the executor
        self.update_username_cache.cancel()
        self.save_memories_periodically.cancel()
        self.executor.shutdown(wait=True)
        await super().close()

# --- Platform Detection ---
def detect_platform(url: str) -> str:
    if 'youtube.com' in url or 'youtu.be' in url:
        return 'youtube'
    if 'tiktok.com' in url:
        return 'tiktok'
    if 'github.com' in url:
        return 'github'
    if 'twitter.com' in url or 'x.com' in url:
        return 'twitter'
    if 'facebook.com' in url or 'fb.watch' in url:
        return 'facebook'
    return 'website'

# --- Platform Handlers (Synchronous) ---
def fetch_video_info_sync(url: str) -> str:
    """Synchronous function to fetch video info."""
    try:
        ydl_opts = {'quiet': True, 'skip_download': True, 'forcejson': True, 'extract_flat': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        summary = f"**Title:** {info.get('title', '')[:100]}\n"
        summary += f"**Uploader:** {info.get('uploader', '')}\n"
        summary += f"**Upload date:** {info.get('upload_date', '')}\n"
        summary += f"**Duration:** {info.get('duration_string', info.get('duration', ''))} seconds\n"
        summary += f"**Views:** {info.get('view_count', '')}\n"
        summary += f"**Description:**\n{info.get('description', '')[:1000]}"
        return summary
    except yt_dlp.utils.DownloadError as e:
        return f"❌ ไม่สามารถดึงข้อมูลวิดีโอได้: {e}"
    except Exception as e:
        return f"❌ เกิดข้อผิดพลาดในการดึงข้อมูลวิดีโอ: {e}"

def fetch_github_info_sync(url: str) -> str:
    """Synchronous function to fetch GitHub info."""
    try:
        m = re.match(r'https?://github.com/([^/]+)/([^/]+)', url)
        if not m: return "Invalid GitHub URL."
        owner, repo = m.group(1), m.group(2)
        g = Github()
        repo_obj = g.get_repo(f"{owner}/{repo}")
        summary = f"**Repository:** {repo_obj.full_name}\n"
        summary += f"**Description:** {repo_obj.description}\n"
        summary += f"**Stars:** {repo_obj.stargazers_count}\n"
        summary += f"**Forks:** {repo_obj.forks_count}\n"
        summary += f"**Open Issues:** {repo_obj.open_issues_count}\n"
        try:
            readme = repo_obj.get_readme().decoded_content.decode('utf-8')
            summary += f"\n**README (first 1000 chars):**\n{readme[:1000]}"
        except Exception:
            summary += "\n(No README found)"
        return summary
    except Exception as e:
        return f"Error fetching GitHub info: {e}"

def fetch_twitter_info_sync(url: str) -> str:
    """Synchronous function to fetch Twitter info."""
    try:
        html = requests.get(url, timeout=10).text
        soup = BeautifulSoup(html, 'html.parser')
        title = soup.find('title').text if soup.find('title') else ''
        return f"**Twitter/X Post Title:** {title}"
    except Exception as e:
        return f"Error fetching Twitter/X info: {e}"

def fetch_facebook_info_sync(url: str) -> str:
    """Synchronous function to fetch Facebook info."""
    try:
        html = requests.get(url, timeout=10).text
        soup = BeautifulSoup(html, 'html.parser')
        title = soup.find('title').text if soup.find('title') else ''
        return f"**Facebook Post Title:** {title}"
    except Exception as e:
        return f"Error fetching Facebook info: {e}"

# --- Enhanced URL Analysis Logic ---
async def analyze_any_url(bot, url: str) -> str:
    """Runs the appropriate synchronous analysis function in the bot's executor."""
    loop = asyncio.get_event_loop()
    platform = detect_platform(url)
    
    if platform == 'youtube' or platform == 'tiktok':
        return await loop.run_in_executor(bot.executor, fetch_video_info_sync, url)
    elif platform == 'github':
        return await loop.run_in_executor(bot.executor, fetch_github_info_sync, url)
    elif platform == 'twitter':
        return await loop.run_in_executor(bot.executor, fetch_twitter_info_sync, url)
    elif platform == 'facebook':
        return await loop.run_in_executor(bot.executor, fetch_facebook_info_sync, url)
    else:
        return await loop.run_in_executor(bot.executor, scrape_website_sync, url)

def main():
    try:
        config = Config()
        bot = DiscordBot(config)
        bot.run(config.discord_bot_token)
    except SystemExit:
        # This is raised by the restart command.
        # We can ignore it as it's an expected part of the restart process.
        logger.info("Bot is restarting...")
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"Bot crashed with an unhandled exception: {e}", exc_info=True)
    finally:
        logger.info("Bot stopped.")

if __name__ == "__main__":
    main()