from flask import Flask
from threading import Thread

app = Flask('Discord-bot-open-port')

@app.route('/')
def index():
  return "Website to open a port in a server running the bot"

def run():
  app.run(host='0.0.0.0', port=8000)

def keep_alive():
  server = Thread(target=run)
  server.start()
  
