from flask import Flask, render_template, request, jsonify
from trading_bot import TradingBot
import threading

app = Flask(__name__)
bot = TradingBot()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify(bot.get_status())

@app.route('/api/start', methods=['POST'])
def start_bot():
    if not bot.is_running:
        bot.start()
        return jsonify({"status": "success", "message": "Bot starting..."})
    return jsonify({"status": "error", "message": "Bot is already running"})

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    if bot.is_running:
        bot.stop()
        return jsonify({"status": "success", "message": "Bot stopping..."})
    return jsonify({"status": "error", "message": "Bot is not running"})

@app.route('/api/settings', methods=['POST'])
def update_settings():
    data = request.json
    if data:
        bot.update_settings(data)
        return jsonify({"status": "success", "message": "Settings updated successfully"})
    return jsonify({"status": "error", "message": "Invalid data"})

if __name__ == '__main__':
    # Use PORT environment variable if available (for production)
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
