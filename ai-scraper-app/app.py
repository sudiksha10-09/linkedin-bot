import os
import json
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, render_template

# --- Dependency Check and Environment Loading ---
# You MUST run: pip install python-dotenv openai requests beautifulsoup4
try:
    from dotenv import load_dotenv 
    load_dotenv()
except ImportError:
    print("FATAL ERROR: python-dotenv not installed. Run 'pip install python-dotenv'.")

# --- OpenAI Client Initialization ---
client = None 
try:
    from openai import OpenAI
    
    # 1. Check if the key exists after loading the .env file
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY environment variable is not set. Check your .env file.")
        
    # 2. Initialize the client (it automatically picks up the key from the environment)
    client = OpenAI()
    print("✅ OpenAI client initialized successfully.")
    
except Exception as e:
    # This block captures any failure during setup (missing key, incorrect import, etc.)
    print("\n" + "="*70)
    print(f"❌ CRITICAL ERROR: OpenAI Client Initialization Failed")
    print(f"Error Type: {type(e).__name__}")
    print(f"Error Detail: {e}")
    print("="*70 + "\n")
    client = None

app = Flask(__name__)

# --- Core Functions ---

def scrape_url(url):
    """Fetches a URL and extracts clean text content."""
    try:
        # Headers help prevent a basic 403 Forbidden error on some sites
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status() # Raise exception for bad status codes (4xx or 5xx)

        soup = BeautifulSoup(response.content, 'html.parser')

        # Remove elements not useful for AI text extraction
        for tag in soup(['script', 'style', 'header', 'footer', 'nav', 'aside']):
            tag.decompose()

        text_content = soup.get_text(separator='\n', strip=True)
        return text_content
    
    except requests.exceptions.HTTPError as e:
        # Specifically catch 4xx or 5xx errors during the HTTP GET request
        return f"Error Scraping: HTTP Error {e.response.status_code} for URL. (Did you try a login page?)"
    except requests.RequestException as e:
        # Catch other request errors like connection timeouts
        return f"Error Scraping: Connection or request issue: {e}"

def extract_with_ai(text_content, instruction):
    """Uses the OpenAI Chat API to intelligently extract data."""
    if not client:
        # This handles the case where client setup failed at the start
        return {"error": "AI client not initialized. Check terminal for configuration errors."}

    system_prompt = (
        "You are an expert data extraction API. Your task is to process the following text "
        "and strictly extract the information based on the user's instruction. "
        "You MUST return the output as a single, valid JSON object, and NOTHING else. "
        "Do not include any introductory or concluding text."
    )

    user_prompt = f"Extraction Instruction: {instruction}\n\n--- Content to process ---\n\n{text_content}"

    try:
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo-0125",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )

        ai_response_text = completion.choices[0].message.content
        return json.loads(ai_response_text)
        
    except json.JSONDecodeError:
        # Catches if the AI returns malformed JSON
        return {"error": "AI returned malformed JSON. Try simplifying your instruction."}
    except Exception as e:
        # Catches general AI errors, most likely AuthenticationError, InvalidRequestError, or RateLimitError
        return {"error": f"AI extraction failed (OpenAI API Error): {type(e).__name__} - {e}"}

# --- Flask Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/extract', methods=['POST'])
def extract_data():
    """API endpoint to receive URL and instruction, then run scraping and AI extraction."""
    data = request.json
    url = data.get('url')
    instruction = data.get('instruction')

    if not url or not instruction:
        return jsonify({"error": "Missing URL or instruction"}), 400

    # 1. Scrape the raw content
    raw_content = scrape_url(url)
    if raw_content.startswith("Error"):
        # Returns the specific scraping error message
        return jsonify({"error": raw_content}), 500

    # 2. Extract structured data using AI (using first 4000 chars to save tokens)
    truncated_content = raw_content[:4000]
    extracted_data = extract_with_ai(truncated_content, instruction)

    # 3. Handle and return results
    if "error" in extracted_data:
        # Returns the specific AI extraction error message
        return jsonify(extracted_data), 500
    
    return jsonify({"data": extracted_data})
# ADD THIS TO THE BOTTOM OF app.py

def test_extraction():
    # Use a URL you know is simple and public
    test_url = "https://en.wikipedia.org/wiki/Python_(programming_language)" 
    test_instruction = "Extract only the main title and the first three sentences of the article. Return as JSON with keys 'name' and 'description'."

    print("\n--- STARTING ISOLATED TEST ---")

    # 1. Test Scraping
    scraped_text = scrape_url(test_url)
    if scraped_text.startswith("Error"):
        print(f"Scraping failed: {scraped_text}")
        return

    print(f"Scraping succeeded. Content size: {len(scraped_text)} characters.")

    # 2. Test AI Extraction
    ai_result = extract_with_ai(scraped_text[:4000], test_instruction)

    print("\n--- AI RESULT ---")
    if "error" in ai_result:
        print(f"AI Extraction Failed: {ai_result['error']}")
    else:
        print("AI Extraction SUCCESS! Result:")
        print(json.dumps(ai_result, indent=2))

    print("--- TEST ENDED ---\n")

# Change the if __name__ == '__main__': block temporarily
if __name__ == '__main__':
    # Comment out the Flask run line and call the test function
    test_extraction()
    # app.run(debug=True)
