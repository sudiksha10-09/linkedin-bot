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
    <title>LinkedIn Stealth Commander</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; background: #f3f2ef; margin: 0; padding: 20px; color: #333; }
        .container { max-width: 800px; margin: 0 auto; }
        .card { background: white; padding: 25px; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        h1 { color: #0a66c2; text-align: center; }
        label { display: block; margin-top: 15px; font-weight: 600; color: #555; }
        input[type="text"], input[type="password"] { 
            width: 100%; padding: 12px; margin-top: 5px; 
            border: 1px solid #ddd; border-radius: 6px; box-sizing: border-box; 
        }
        .help-text { font-size: 0.85em; color: #666; background: #eef3f8; padding: 10px; border-radius: 5px; margin-top: 5px;}
        button { width: 100%; padding: 14px; border: none; border-radius: 6px; font-weight: 700; cursor: pointer; margin-top: 20px; font-size: 1em; }
        .btn-start { background: #0a66c2; color: white; }
        .btn-stop { background: #d11124; color: white; }
        .log-box { background: #1b1f23; color: #00ff00; height: 250px; overflow-y: auto; padding: 15px; font-family: monospace; font-size: 0.85em; border-radius: 6px; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>LinkedIn Stealth Commander</h1>
            
            <div id="setup-form">
                <label>Target Keyword</label>
                <input type="text" id="keyword" placeholder="e.g. Hiring Software Engineers" value="Recruitment">

                <label>Your LinkedIn "li_at" Cookie</label>
                <input type="password" id="cookie" placeholder="Paste your li_at cookie string here...">
                <div class="help-text">
                    <b>Desktop Instructions:</b> Open LinkedIn > Right Click > Inspect > Application > Cookies > Copy "li_at" value.
                </div>
                
                <button onclick="startBot()" class="btn-start" id="startBtn">🚀 Start Bot</button>
            </div>

            <div id="stop-area" style="display:none;">
                <p>Status: <b id="status-text">Running...</b></p>
                <button onclick="stopBot()" class="btn-stop">Stop Session</button>
            </div>

            <div class="log-box" id="log-container">Ready. Waiting for inputs...</div>
        </div>
    </div>

    <script>
        function startBot() {
            const keyword = document.getElementById('keyword').value;
            const cookie = document.getElementById('cookie').value;
            
            if(!cookie) { alert("Cookie is required!"); return; }

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
                document.getElementById('startBtn').innerText = "🚀 Start Bot";
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
        BOT_STATE["logs"] = ["Initializing Stealth Agent..."]
        
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
            log("⚙️ Launching Stealth Browser...")
            # STEALTH ARGUMENTS to bypass "Robot" detection
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--disable-gpu'
                ]
            )
            
            # Use a real Windows User Agent
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720},
                ignore_https_errors=True
            )
            
            # Inject Cookie
            log("🍪 Injecting Session Cookie...")
            context.add_cookies([{
                "name": "li_at",
                "value": cookie,
                "domain": ".linkedin.com",
                "path": "/"
            }])
            
            page = context.new_page()
            
            # STEP 1: Go to Feed (Warm up)
            log("🌍 Navigating to LinkedIn Feed (90s timeout)...")
            try:
                # wait_until='domcontentloaded' prevents waiting for slow tracking scripts
                page.goto("https://www.linkedin.com/feed/", timeout=90000, wait_until="domcontentloaded")
            except Exception as e:
                log(f"⚠️ Initial load slow: {str(e)[:50]}... (Continuing)")

            time.sleep(5)

            # Check if login worked
            if "login" in page.url or "signup" in page.url:
                 log("❌ Login Failed. Your 'li_at' cookie is expired or incorrect.")
                 log("👉 Please refresh your LinkedIn tab and get a new cookie.")
                 return

            log(f"✅ Login Verified! Connected to LinkedIn.")
            
            # STEP 2: Go to Search
            log(f"🔎 Searching for: {keyword}...")
            search_url = f"https://www.linkedin.com/search/results/content/?keywords={urllib.parse.quote(keyword)}&sortBy=%22date_posted%22"
            
            try:
                page.goto(search_url, timeout=60000, wait_until="domcontentloaded")
            except Exception as e:
                 log(f"⚠️ Search load slow: {str(e)[:50]}...")

            time.sleep(5)

            # STEP 3: Scroll Loop
            for i in range(5):
                if not BOT_STATE["is_running"]: break
                log(f"📜 Scanning Page {i+1}...")
                
                # Check for Auth Wall
                if "auth/wall" in page.url or "challenge" in page.url:
                    log("❌ LinkedIn Security Check triggered.")
                    break
                
                # Scroll down
                try:
                    page.evaluate("window.scrollBy(0, 800)")
                except:
                    pass
                
                time.sleep(3)
                
            log("✅ Session Finished Successfully.")

    except Exception as e:
        log(f"❌ Critical Error: {e}")
    finally:
        if browser: 
            try: browser.close()
            except: pass
        BOT_STATE["is_running"] = False

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
