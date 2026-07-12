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
    # Fix for Python 3.13 event loop
    asyncio.set_event_loop(asyncio.new_event_loop())
    main_game_bot.main()

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
