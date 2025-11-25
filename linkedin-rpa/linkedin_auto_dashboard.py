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

# Setup OpenAI (Optional - leave blank if you don't have a key)
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

# --- HTML DASHBOARD (Identical to before) ---
HTML_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LinkedIn Cloud Commander</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; background: #f3f2ef; margin: 0; padding: 20px; color: #333; }
        .header { text-align: center; margin-bottom: 30px; }
        .header h1 { color: #0a66c2; margin: 0; }
        .container { display: grid; grid-template-columns: 1fr 2fr; gap: 20px; max-width: 1200px; margin: 0 auto; }
        @media (max-width: 768px) { .container { grid-template-columns: 1fr; } }
        .card { background: white; padding: 25px; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        label { display: block; margin-top: 12px; font-weight: 600; font-size: 0.85em; color: #555; }
        input[type="text"], input[type="password"], input[type="number"] { 
            width: 100%; padding: 10px; margin-top: 5px; 
            border: 1px solid #ddd; border-radius: 6px; box-sizing: border-box; font-size: 1em;
        }
        .checkbox-group { display: flex; gap: 15px; margin-top: 8px; }
        button { width: 100%; padding: 12px; border: none; border-radius: 6px; font-weight: 700; cursor: pointer; margin-top: 20px; font-size: 1em; transition: 0.2s; }
        .btn-start { background: #0a66c2; color: white; }
        .btn-stop { background: #d11124; color: white; }
        .log-box { background: #1b1f23; color: #4caf50; height: 150px; overflow-y: auto; padding: 15px; font-family: monospace; font-size: 0.8em; border-radius: 6px; margin-top: 20px; }
        .draft-item { border: 1px solid #e0e0e0; background: #fff; border-radius: 8px; padding: 15px; margin-bottom: 15px; }
        .ai-suggestion { background: #eef3f8; padding: 10px; border-radius: 6px; margin-bottom: 10px; color: #222; font-weight: 500; }
        .action-row { display: flex; gap: 10px; }
        .btn-post { background: #057642; color: white; flex: 2; margin-top: 0; padding: 8px; }
        .btn-discard { background: #fff; border: 1px solid #ccc; color: #666; flex: 1; margin-top: 0; padding: 8px; }
        .badge { padding: 4px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; }
        .badge-posted { background: #d4edda; color: #155724; }
        .badge-discarded { background: #f8d7da; color: #721c24; }
    </style>
</head>
<body>
    <div class="header">
        <h1>LinkedIn Cloud Commander</h1>
        <p>Hosted Online</p>
    </div>
    <div class="container">
        <div class="card">
            <h2>Configuration</h2>
            <div id="setup-form">
                <label>LinkedIn Email</label>
                <input type="text" id="email" placeholder="email@example.com">
                <label>LinkedIn Password</label>
                <input type="password" id="password" placeholder="••••••••">
                <hr style="margin: 20px 0; border: 0; border-top: 1px solid #eee;">
                <label>Search Keyword</label>
                <input type="text" id="keyword" placeholder="e.g. AI Marketing">
                <label>Max Posts</label>
                <input type="number" id="max_posts" value="5" min="1" max="15">
                <div class="checkbox-group">
                    <label><input type="checkbox" id="deg1" checked> 1st</label>
                    <label><input type="checkbox" id="deg2" checked> 2nd</label>
                    <label><input type="checkbox" id="deg3"> 3rd+</label>
                </div>
                <button onclick="startBot()" class="btn-start" id="startBtn">Initialize Bot</button>
            </div>
            <div id="stop-area" style="display:none;">
                <p>Status: <b id="status-text" style="color:#0a66c2;">Running...</b></p>
                <p style="font-size:0.8em; text-align:center;">Found <span id="found-count">0</span> / <span id="target-count">0</span> posts</p>
                <button onclick="stopBot()" class="btn-stop">Stop Session</button>
            </div>
            <div class="log-box" id="log-container">System Ready...</div>
        </div>
        <div class="card">
            <h2>Live Feed</h2>
            <div id="drafts-container">Waiting for activity...</div>
        </div>
    </div>
    <script>
        function startBot() {
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            const keyword = document.getElementById('keyword').value;
            const max_posts = document.getElementById('max_posts').value;
            let filters = [];
            if(document.getElementById('deg1').checked) filters.push("F");
            if(document.getElementById('deg2').checked) filters.push("S");
            if(document.getElementById('deg3').checked) filters.push("O");
            if(!email || !password || !keyword) { alert("Credentials required."); return; }
            document.getElementById('startBtn').disabled = true;
            document.getElementById('startBtn').innerText = "Connecting...";
            fetch('/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, password, keyword, max_posts, filters})
            });
        }
        function stopBot() { fetch('/stop', {method: 'POST'}); }
        function handleDraft(id, action) {
            document.getElementById('actions-'+id).innerHTML = `<span>Processing...</span>`;
            fetch('/handle_draft', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id, action})
            });
        }
        setInterval(async () => {
            const res = await fetch('/status');
            const data = await res.json();
            if (data.is_running) {
                document.getElementById('setup-form').style.display = 'none';
                document.getElementById('stop-area').style.display = 'block';
                document.getElementById('status-text').innerText = data.status;
                document.getElementById('found-count').innerText = data.stats.scanned;
                document.getElementById('target-count').innerText = data.stats.target;
            } else {
                document.getElementById('setup-form').style.display = 'block';
                document.getElementById('stop-area').style.display = 'none';
                document.getElementById('startBtn').disabled = false;
                document.getElementById('startBtn').innerText = "Initialize Bot";
            }
            const logBox = document.getElementById('log-container');
            logBox.innerText = data.logs.join("\\n");
            logBox.scrollTop = logBox.scrollHeight; 
            const draftBox = document.getElementById('drafts-container');
            if (data.drafts.length > 0) {
                let html = "";
                data.drafts.slice().reverse().forEach(d => {
                    let actionArea = "";
                    if (d.status === 'pending') {
                        actionArea = `
                            <div class="action-row" id="actions-${d.id}">
                                <button class="btn-post" onclick="handleDraft('${d.id}', 'post')">Post</button>
                                <button class="btn-discard" onclick="handleDraft('${d.id}', 'discard')">Discard</button>
                            </div>`;
                    } else if (d.status === 'posted') actionArea = `<span class="badge badge-posted">✅ Posted</span>`;
                    else actionArea = `<span class="badge badge-discarded">❌ Discarded</span>`;
                    html += `<div class="draft-item"><div class="post-text">"${d.text.substring(0, 100)}..."</div><div class="ai-suggestion">🤖 ${d.ai_reply}</div>${actionArea}</div>`;
                });
                draftBox.innerHTML = html;
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
        BOT_STATE["logs"] = ["Initializing Cloud Agent..."]
        BOT_STATE["drafts"] = []
        BOT_STATE["stats"] = {"scanned": 0, "target": int(data.get('max_posts', 5))}
        global ELEMENT_STORE
        ELEMENT_STORE = {}
        t = threading.Thread(target=bot_logic, args=(
            data['email'], data['password'], data['keyword'], int(data.get('max_posts', 5)), data.get('filters', [])
        ))
        t.daemon = True
        t.start()
    return jsonify({"msg": "Started"})

@app.route("/stop", methods=["POST"])
def stop_route():
    BOT_STATE["is_running"] = False
    return jsonify({"msg": "Stopping"})

@app.route("/handle_draft", methods=["POST"])
def handle_draft():
    data = request.json
    draft_id = data['id']
    action = data['action']
    for d in BOT_STATE["drafts"]:
        if d['id'] == draft_id:
            d['status'] = 'posting...' if action == 'post' else 'discarded'
    COMMAND_QUEUE.put({"id": draft_id, "action": action})
    return jsonify({"msg": "OK"})

# --- BOT LOGIC ---
def log(msg):
    t = datetime.now().strftime("%H:%M:%S")
    line = f"[{t}] {msg}"
    print(line)
    BOT_STATE["logs"].append(line)
    BOT_STATE["status"] = msg

def generate_ai_comment(text, keyword):
    if not openai_client: return f"Great post about {keyword}!"
    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system", "content": "You are a friendly LinkedIn user. Write a 1-sentence comment."},
                {"role":"user", "content": f"Post: {text}\nTopic: {keyword}"}
            ], max_tokens=60
        )
        return resp.choices[0].message.content.strip()
    except: return f"Great insights on {keyword}."

def bot_logic(email, password, keyword, max_posts, filters):
    with sync_playwright() as p:
        try:
            # HEADLESS MUST BE TRUE FOR CLOUD HOSTING
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            log("Navigating to LinkedIn...")
            page.goto("https://www.linkedin.com/login")
            time.sleep(2)
            
            if page.query_selector("#username"):
                page.fill("#username", email)
                page.fill("#password", password)
                page.click("button[type=submit]")
            
            log("Waiting for login (10s)...")
            time.sleep(10) 

            # Verification check
            if "challenge" in page.url or "security" in page.url:
                log("⚠️ CAPTCHA DETECTED. Cannot solve in Headless mode.")
                return

            base_url = f"https://www.linkedin.com/search/results/content/?keywords={urllib.parse.quote(keyword)}&sortBy=%22date_posted%22"
            if filters:
                json_inner = ",".join([f'"{f}"' for f in filters]) 
                base_url += f"&network=%5B{json_inner}%5D"

            log(f"Searching '{keyword}'...")
            page.goto(base_url)
            time.sleep(5)

            scanned_hashes = set()
            found_count = 0
            
            while BOT_STATE["is_running"] and found_count < max_posts:
                log(f"Scanning feed... ({found_count}/{max_posts})")
                page.evaluate("window.scrollBy(0, 500)")
                time.sleep(2)
                
                posts = page.query_selector_all(".update-components-text")
                if not posts: posts = page.query_selector_all(".feed-shared-update-v2")

                for post in posts:
                    if found_count >= max_posts: break
                    if not BOT_STATE["is_running"]: break
                    
                    try:
                        text_content = post.inner_text().strip()
                        if len(text_content) < 20: continue
                        h = str(hash(text_content))
                        if h in scanned_hashes: continue
                        scanned_hashes.add(h)

                        ai_reply = generate_ai_comment(text_content, keyword)
                        uid = str(uuid.uuid4())[:8]
                        ELEMENT_STORE[uid] = post 
                        
                        BOT_STATE["drafts"].append({
                            "id": uid, "text": text_content, "ai_reply": ai_reply, "status": "pending"
                        })
                        found_count += 1
                        BOT_STATE["stats"]["scanned"] = found_count
                        log(f"✅ Found post! Waiting for approval...")
                        
                        while True:
                            if not BOT_STATE["is_running"]: break
                            d_check = next((d for d in BOT_STATE["drafts"] if d['id'] == uid), None)
                            if d_check and d_check['status'] != 'pending': break
                            time.sleep(0.5)
                        
                        process_queue(page)
                    except Exception as e: continue
                time.sleep(1)

        except Exception as e:
            log(f"Error: {e}")
        finally:
            browser.close()
            BOT_STATE["is_running"] = False

def process_queue(page):
    while not COMMAND_QUEUE.empty():
        cmd = COMMAND_QUEUE.get()
        d_id = cmd['id']
        if cmd['action'] == 'post' and d_id in ELEMENT_STORE:
            execute_post(page, ELEMENT_STORE[d_id], d_id)
        if d_id in ELEMENT_STORE: del ELEMENT_STORE[d_id]

def execute_post(page, handle, d_id):
    try:
        log("Posting comment...")
        btn = handle.query_selector("button[aria-label='Comment']")
        if not btn: btn = handle.query_selector(".comment-button")
        if btn: 
            btn.click()
            time.sleep(1)
            page.keyboard.type(next(d['ai_reply'] for d in BOT_STATE['drafts'] if d['id'] == d_id))
            time.sleep(1)
            submit = handle.query_selector(".comments-comment-box__submit-button--cr")
            if not submit: submit = handle.query_selector("button.comments-comment-box__submit-button")
            if submit: 
                submit.click()
                log("✅ Comment published.")
                time.sleep(2)
    except Exception as e: log(f"❌ Post failed: {e}")

if __name__ == "__main__":
    # AUTOMATIC PORT CONFIGURATION FOR CLOUD
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)