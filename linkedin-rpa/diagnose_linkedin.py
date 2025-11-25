# diagnose2_linkedin.py
"""More exhaustive LinkedIn DOM diagnostic for Playwright.
Run this with your venv active. After login, make sure the Playwright-opened browser
is the one you scroll — then press Enter in the terminal to run diagnostic.
This script prints page URL, body text length, and counts + sample outerHTML
for many candidate selectors LinkedIn uses for posts and comment areas.
"""

import time
import urllib.parse
from getpass import getpass
from playwright.sync_api import sync_playwright

SELECTORS_TO_CHECK = [
    "article",
    "div.feed-shared-update-v2",
    "div.update-components",
    "div.feed-shared-text__text-view",
    "div.occludable-update",
    "div[data-urn]",
    "div[data-entity-urn]",
    "div.feed-shared-inline-show-more-text",
    "div.feed-shared-actor__content",
    "div.update-components__container",
    "div.feed-shared-update-v2__description",
    "div.feed-shared-actor__name",
    "div.feed-shared-update-v2__commentary",
    "div[role='article']",
    "div[role='feed']",
    '[data-control-name="comments"]',
    'button[aria-label*="Comment"]',
    'div[role="textbox"]',
    'div[contenteditable="true"]'
]

def print_sample(els, limit=3):
    out = []
    for e in els[:limit]:
        try:
            html = e.inner_html()[:800].replace("\n", " ")
            text = e.inner_text()[:400].replace("\n", " ")
            out.append({"html": html, "text": text})
        except Exception as ex:
            out.append({"error": str(ex)})
    return out

def main():
    email = input("LinkedIn email: ").strip()
    password = getpass("LinkedIn password: ").strip()
    keyword = input("Search keyword (e.g., sports, football): ").strip()
    if not email or not password or not keyword:
        print("All inputs required. Exiting.")
        return

    search_url = "https://www.linkedin.com/search/results/content/?keywords=" + urllib.parse.quote(keyword)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=80)
        ctx = browser.new_context()
        page = ctx.new_page()

        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        page.fill('input[name="session_key"]', email)
        page.fill('input[name="session_password"]', password)
        page.click('button[type="submit"]')
        print("Logging in... wait for the page to load.")
        try:
            page.wait_for_selector('input[placeholder="Search"]', timeout=20000)
            print("Login OK.")
        except Exception:
            print("If verification is required, complete it in the opened browser, then press Enter here.")
            input("Press Enter after finishing verification in browser...")

        # Go to search results page
        page.goto(search_url, wait_until="domcontentloaded")
        time.sleep(1.2)

        # If 'Posts' filter exists, try to click it to ensure content is posts
        try:
            btn = page.query_selector('button:has-text("Posts")')
            if btn:
                btn.click()
                time.sleep(1.0)
        except Exception:
            pass

        print("\nNow: manually scroll in the PLAYWRIGHT browser window until you see posts (2-3 page downs),")
        print("then wait a few seconds and press Enter here to let the script inspect the DOM.")
        input("Press Enter after you have scrolled and posts are visible in the Playwright browser...")

        # wait a little to allow lazy loading
        time.sleep(2.0)

        # basic page fingerprint
        try:
            url = page.url
        except:
            url = "unable to read url"
        try:
            body_text = page.evaluate("() => document.body.innerText.length")
        except:
            body_text = -1

        print("\nPAGE URL:", url)
        print("BODY TEXT LENGTH:", body_text)
        print("Now checking selectors... (will print count and up to 3 samples for each)\n")

        for sel in SELECTORS_TO_CHECK:
            try:
                els = page.query_selector_all(sel)
                count = len(els)
                print(f"Selector: {sel} -> count: {count}")
                if count > 0:
                    samples = print_sample(els, limit=3)
                    for idx, s in enumerate(samples, 1):
                        print(f"  Sample #{idx} text (first 200 chars): {s.get('text','')[:200]}")
                        print(f"  Sample #{idx} html (truncated): {s.get('html','')[:300]}")
                print("-"*60)
            except Exception as e:
                print(f"Selector {sel} -> error: {e}")
                print("-"*60)

        # For convenience, print number of total 'article'-like nodes using a JS probe
        try:
            probe = page.evaluate("""
                () => {
                  const nodes = Array.from(document.querySelectorAll('*'));
                  const topTags = {};
                  nodes.slice(0, 5000).forEach(n => { topTags[n.tagName] = (topTags[n.tagName]||0) + 1; });
                  // return top 12 tags and their counts
                  return Object.entries(topTags).sort((a,b)=>b[1]-a[1]).slice(0,12);
                }
            """)
            print("\nTop tag counts (sample):", probe)
        except Exception:
            pass

        print("\nDiagnostic finished. Copy the sample block for any selector that had count>0 and paste here.")
        input("Press Enter to close browser and exit...")
        ctx.close()
        browser.close()

if __name__ == "__main__":
    main()
