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

# Setup OpenAI (Optional)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
try:
    from openai import OpenAI
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
except:
    openai_client = None

# --- Global State ---
# We track state per "session" if possible, but for simplicity here we keep one global state
# In a real production app, you would need a database.
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
    <title>LinkedIn Cloud Commander (Multi-User)</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; background: #f3f2ef; margin: 0; padding: 20px; color: #333; }
        .container { max-width: 900px; margin: 0 auto; display: grid; gap: 20px; }
        .card { background: white; padding: 25px; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        h1 { color: #0a66c2; text-align: center; margin-top: 0; }
        label { display: block; margin-top: 12px; font-weight: 600; font-size: 0.85em; color: #555; }
        input[type="text"], input[type="password"] { 
            width: 100%; padding: 10px; margin-top: 5px; 
            border: 1px solid #ddd; border-radius: 6px; box-sizing: border-box; 
        }
        .help-text { font-size: 0.8em; color: #666; margin-top: 5px; background: #eef3f8; padding: 10px; border-radius: 5px; }
        button { width: 100%; padding: 12px; border: none; border-radius: 6px; font-weight: 700; cursor: pointer; margin-top: 20px; font-size: 1em; transition: 0.2s; }
        .btn-start { background: #0a66c2; color: white; }
        .btn-stop { background: #d11124; color: white; }
        .log-box { background: #1b1f23; color: #4caf50; height: 150px; overflow-y: auto; padding: 15px; font-family: monospace; font-size: 0.8em; border-radius: 6px; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>LinkedIn Cloud Commander</h1>
            
            <div id="setup-form">
                <label>Target Keyword</label>
                <input type="text" id="keyword" placeholder="e.g. Generative AI" value="Software Engineering">

                <label>Your LinkedIn "li_at" Cookie</label>
                <input type="password" id="cookie" placeholder="Paste long cookie string here...">
                <div class="help-text">
                    <b>How to get this?</b><br>
                    1. Go to LinkedIn.com (make sure you are logged in).<br>
                    2. Right-Click > Inspect > Application Tab > Cookies.<br>
                    3. Copy the value of <b>li_at</b> and paste it here.
                </div>
                
                <button onclick="startBot()" class="btn-start" id="startBtn">🚀 Launch Bot</button>
            </div>

            <div id="stop-area" style="display:none;">
                <p>Status: <b id="status-text" style="color:#0a66c2;">Running...</b></p>
                <button onclick="stopBot()" class="btn-stop">Stop Session</button>
            </div>

            <div class="log-box" id="log-container">Waiting for user inputs...</div>
        </div>
    </div>

    <script>
        function startBot() {
            const keyword = document.getElementById('keyword').value;
            const cookie = document.getElementById('cookie').value;
            
            if(!cookie) { alert("You must provide the li_at cookie!"); return; }

            document.getElementById('startBtn').disabled = true;
            document.getElementById('startBtn').innerText = "Starting...";

            fetch('/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({keyword, cookie})
            });
        }

        function stopBot() { fetch('/stop', {method: 'POST'}); }

        setInterval(async () => {
            const res = await fetch('/status');
            const data = await res.json();

            if (data.is_running) {
                document.getElementById('setup-form').style.display = 'none';
                document.getElementById('stop-area').style.display = 'block';
                document.getElementById('status-text').innerText = data.status;
            } else {
                document.getElementById('setup-form').style.display = 'block';
                document.getElementById('stop-area').style.display = 'none';
                document.getElementById('startBtn').disabled = false;
                document.getElementById('startBtn').innerText = "🚀 Launch Bot";
            }
            
            const logBox = document.getElementById('log-container');
            logBox.innerText = data.logs.join("\\n");
            logBox.scrollTop = logBox.scrollHeight; 
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
        
        # WE GET THE COOKIE FROM THE USER NOW, NOT THE SERVER
        user_cookie = data.get('cookie')
        user_keyword = data.get('keyword')
        
        t = threading.Thread(target=bot_logic, args=(user_cookie, user_keyword))
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

def bot_logic(cookie, keyword):
    browser = None
    try:
        with sync_playwright() as p:
            # HEADLESS TRUE FOR CLOUD
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            # --- INJECT USER'S COOKIE ---
            log("🍪 Using provided session cookie...")
            context.add_cookies([{
                "name": "li_at",
                "value": cookie,
                "domain": ".linkedin.com",
                "path": "/"
            }])
            
            page = context.new_page()
            
            log("Navigating to LinkedIn (60s timeout)...")
            
            # --- THE FIX IS HERE ---
            # 1. timeout=60000: Give it 60 seconds instead of 30
            # 2. wait_until="domcontentloaded": Don't wait for images, just text/structure
            try:
                page.goto("https://www.linkedin.com/", timeout=60000, wait_until="domcontentloaded")
            except Exception as e:
                log("⚠️ Page load took a while, but continuing...")

            time.sleep(5) # Give it a moment to settle

            # Check if it worked
            if "login" in page.url and "feed" not in page.url:
                 log("❌ Login Failed. The cookie is invalid or expired.")
                 return

            log(f"✅ Success! Logged in without password.")
            log(f"🔎 Searching for: {keyword}...")

            # Simple Search Action
            search_url = f"https://www.linkedin.com/search/results/content/?keywords={urllib.parse.quote(keyword)}"
            page.goto(search_url, timeout=60000, wait_until="domcontentloaded")
            time.sleep(5)
            
            # Simple Scroll Loop
            for i in range(5):
                if not BOT_STATE["is_running"]: break
                log(f"Processing page {i+1}...")
                page.evaluate("window.scrollBy(0, 500)")
                time.sleep(2)
                
            log("Task complete.")

    except Exception as e:
        log(f"Error: {e}")
    finally:
        if browser: browser.close()
        BOT_STATE["is_running"] = False
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
