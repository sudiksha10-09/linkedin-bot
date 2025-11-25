import os
import time
import threading
import uuid
import urllib.parse
from datetime import datetime
from queue import Queue

# Third-party installs
from flask import Flask, render_template_string, request, jsonify
from playwright.sync_api import sync_playwright

# Setup OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
try:
    from openai import OpenAI
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
except:
    openai_client = None

# --- Global State ---
ELEMENT_STORE = {} 
BOT_STATE = {
    "is_running": False,
    "status": "Idle",
    "logs": [],
    "drafts": [], 
    "stats": {"scanned": 0, "target": 0}
}
COMMAND_QUEUE = Queue()

app = Flask(__name__)

# --- HTML DASHBOARD ---
HTML_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LinkedIn Cloud Commander</title>
    <style>
        body { font-family: sans-serif; background: #f3f2ef; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        h1 { color: #0a66c2; text-align: center; }
        .log-box { background: #1b1f23; color: #4caf50; height: 200px; overflow-y: auto; padding: 15px; font-family: monospace; border-radius: 6px; margin-top: 20px; }
        button { padding: 10px 20px; cursor: pointer; background: #0a66c2; color: white; border: none; border-radius: 5px; font-weight: bold; }
        button.stop { background: #d11124; }
        input { padding: 8px; width: 60%; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>LinkedIn Cloud Commander</h1>
        
        <div id="controls">
            <h3>Configuration</h3>
            <p><b>Note:</b> Login is handled via Cookies in Environment Variables.</p>
            <input type="text" id="keyword" placeholder="Enter Search Keyword (e.g. AI Marketing)" value="AI Technology">
            <br>
            <button onclick="startBot()" id="startBtn">Start Bot</button>
            <button onclick="stopBot()" class="stop">Stop Bot</button>
        </div>

        <div class="log-box" id="log-container">System Ready...</div>
    </div>

    <script>
        function startBot() {
            const keyword = document.getElementById('keyword').value;
            document.getElementById('startBtn').disabled = true;
            document.getElementById('startBtn').innerText = "Running...";
            fetch('/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({keyword: keyword})
            });
        }
        function stopBot() { fetch('/stop', {method: 'POST'}); }

        setInterval(async () => {
            const res = await fetch('/status');
            const data = await res.json();
            const logBox = document.getElementById('log-container');
            logBox.innerText = data.logs.join("\\n");
            logBox.scrollTop = logBox.scrollHeight;
            
            if (!data.is_running) {
                 document.getElementById('startBtn').disabled = false;
                 document.getElementById('startBtn').innerText = "Start Bot";
            }
        }, 1000);
    </script>
</body>
</html>
"""

# --- FLASK ROUTES ---
@app.route("/")
def index(): return render_template_string(HTML_TEMPLATE)

@app.route("/status")
def status(): return jsonify(BOT_STATE)

@app.route("/start", methods=["POST"])
def start_route():
    data = request.json
    if not BOT_STATE["is_running"]:
        BOT_STATE["is_running"] = True
        BOT_STATE["logs"] = ["Initializing..."]
        # Use Environment variables for login
        email = os.getenv("LI_EMAIL", "")
        password = os.getenv("LI_PASS", "")
        cookie = os.getenv("LI_COOKIE", "")
        
        t = threading.Thread(target=bot_logic, args=(email, password, cookie, data.get('keyword', 'AI')))
        t.daemon = True
        t.start()
    return jsonify({"msg": "Started"})

@app.route("/stop", methods=["POST"])
def stop_route():
    BOT_STATE["is_running"] = False
    return jsonify({"msg": "Stopping"})

# --- BOT LOGIC ---
def log(msg):
    t = datetime.now().strftime("%H:%M:%S")
    BOT_STATE["logs"].append(f"[{t}] {msg}")
    print(msg)

def bot_logic(email, password, cookie, keyword):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # INJECT COOKIE IF AVAILABLE
        if cookie:
            log("🍪 Injecting Session Cookie...")
            context.add_cookies([{
                "name": "li_at",
                "value": cookie,
                "domain": ".linkedin.com",
                "path": "/"
            }])
        
        page = context.new_page()
        
        try:
            log("Navigating to LinkedIn...")
            page.goto("https://www.linkedin.com/")
            time.sleep(3)

            # Check if logged in
            if "feed" not in page.url and "login" in page.url:
                log("⚠️ Cookie failed or expired. Trying Password login...")
                page.goto("https://www.linkedin.com/login")
                page.fill("#username", email)
                page.fill("#password", password)
                page.click("button[type=submit]")
                time.sleep(5)

            if "challenge" in page.url or "security" in page.url:
                log("❌ CAPTCHA BLOCKED. You must update your LI_COOKIE in Render.")
                return

            log(f"✅ Login Successful! Searching for {keyword}...")
            
            # Simple Search & Scroll Demo
            search_url = f"https://www.linkedin.com/search/results/content/?keywords={urllib.parse.quote(keyword)}"
            page.goto(search_url)
            time.sleep(5)
            
            for i in range(5):
                if not BOT_STATE["is_running"]: break
                log(f"Scanning page {i+1}...")
                page.evaluate("window.scrollBy(0, 500)")
                time.sleep(2)
            
            log("Session finished successfully.")

        except Exception as e:
            log(f"Error: {e}")
        finally:
            browser.close()
            BOT_STATE["is_running"] = False

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
