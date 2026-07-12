import os
import threading
import asyncio
from flask import Flask
import main_game_bot

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running! 🤖"

@app.route('/health')
def health():
    return "OK", 200

def run_bot():
    """Run the bot with proper event loop handling"""
    try:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the bot
        main_game_bot.main()
        
    except Exception as e:
        print(f"Bot error: {e}")
    finally:
        loop.close()

if __name__ == "__main__":
    # Run bot in background thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Run web server
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
