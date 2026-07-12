import os
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

if __name__ == "__main__":
    # Create and set event loop for the main thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Run the bot
        loop.run_until_complete(main_game_bot.main())
    except KeyboardInterrupt:
        print("Bot stopped")
    finally:
        loop.close()
