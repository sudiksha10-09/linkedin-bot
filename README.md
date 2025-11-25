# LinkedIn OAuth Demo (personal member)

## Quick start (step-by-step)

1. Clone/download project into `linkedin-oauth-demo/`.
2. Run `npm install` to install deps.
3. Copy `.env.example` to `.env` and fill:
   - LINKEDIN_CLIENT_ID (from your LinkedIn app)
   - LINKEDIN_CLIENT_SECRET (from your LinkedIn app)
   - REDIRECT_URI (you will use ngrok to create HTTPS URL; replace as described below)
   - PORT (optional, default 3000)

4. Run ngrok to expose local server:
   - Install ngrok from https://ngrok.com/
   - Start ngrok: `ngrok http 3000`
   - Copy the HTTPS URL it gives you (example: `https://abcd-1234.ngrok.io`)
   - In your LinkedIn Developer app settings, set Redirect URI to:
     `https://abcd-1234.ngrok.io/auth/linkedin/callback`
   - Also update `REDIRECT_URI` in your `.env` to that same ngrok URL + `/auth/linkedin/callback`

5. Start the server:
