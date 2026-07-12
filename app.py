import os
import threading
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
    main_game_bot.main()

if __name__ == "__main__":
    # Run bot in background
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Run web server
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
