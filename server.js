// server.js
require('dotenv').config();
const express = require('express');
const cookieParser = require('cookie-parser');
const axios = require('axios');
const { v4: uuidv4 } = require('uuid');
const { saveToken, loadToken } = require('./helpers/tokenStore');

const app = express();
app.use(cookieParser());
app.use(express.json());

const {
  LINKEDIN_CLIENT_ID,
  LINKEDIN_CLIENT_SECRET,
  REDIRECT_URI,
  PORT = 3000,
  STATE_SECRET = 'state_secret_placeholder'
} = process.env;

if (!LINKEDIN_CLIENT_ID || !LINKEDIN_CLIENT_SECRET || !REDIRECT_URI) {
  console.error('ERROR: Please set LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET and REDIRECT_URI in .env');
  process.exit(1);
}

// 1) Start OAuth: redirect user to LinkedIn authorization screen
app.get('/auth/linkedin', (req, res) => {
  const state = uuidv4();
  // store the state in a cookie to verify later (CSRF protection)
  res.cookie('oauth_state', state, { httpOnly: true, sameSite: 'lax' });

  const params = new URLSearchParams({
    response_type: 'code',
    client_id: LINKEDIN_CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    scope: 'r_liteprofile r_emailaddress w_member_social',
    state
  });

  const url = `https://www.linkedin.com/oauth/v2/authorization?${params.toString()}`;
  res.redirect(url);
});

// 2) Callback: LinkedIn redirects here with ?code=...&state=...
app.get('/auth/linkedin/callback', async (req, res) => {
  try {
    const { code, state } = req.query;
    const savedState = req.cookies['oauth_state'];

    if (!code) return res.status(400).send('Missing code in callback.');
    if (!state || !savedState || state !== savedState) {
      return res.status(400).send('Invalid state (possible CSRF).');
    }

    // Exchange code for access token (server-side)
    const tokenResponse = await axios.post(
      'https://www.linkedin.com/oauth/v2/accessToken',
      new URLSearchParams({
        grant_type: 'authorization_code',
        code,
        redirect_uri: REDIRECT_URI,
        client_id: LINKEDIN_CLIENT_ID,
        client_secret: LINKEDIN_CLIENT_SECRET
      }).toString(),
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
    );

    const tokenData = tokenResponse.data;
    // tokenData: { access_token: "...", expires_in: 5184000 }
    const saved = {
      access_token: tokenData.access_token,
      expires_at: Date.now() + (tokenData.expires_in * 1000),
      fetched_at: new Date().toISOString()
    };
    saveToken(saved);

    // fetch basic profile to verify token
    const profileRes = await axios.get('https://api.linkedin.com/v2/me', {
      headers: {
        Authorization: `Bearer ${saved.access_token}`,
        'X-Restli-Protocol-Version': '2.0.0'
      }
    });

    const emailRes = await axios.get('https://api.linkedin.com/v2/emailAddress?q=members&projection=(elements*(handle~))', {
      headers: {
        Authorization: `Bearer ${saved.access_token}`,
        'X-Restli-Protocol-Version': '2.0.0'
      }
    });

    res.send(`
      <h2>LinkedIn connected ✅</h2>
      <p>Your access token is saved locally (tokens.json).</p>
      <h3>Profile (from /v2/me)</h3>
      <pre>${JSON.stringify(profileRes.data, null, 2)}</pre>
      <h3>Email</h3>
      <pre>${JSON.stringify(emailRes.data, null, 2)}</pre>
      <p>Next: we can generate reply drafts and then post after your approval.</p>
      <p><a href="/">Return home</a></p>
    `);
  } catch (err) {
    console.error('Callback error:', err.response?.data || err.message);
    res.status(500).send('OAuth callback error: ' + (err.response?.data?.error_description || err.message));
  }
});

app.get('/', (req, res) => {
  const token = loadToken();
  res.send(`
    <h1>LinkedIn OAuth Demo</h1>
    <p><a href="/auth/linkedin">Connect with LinkedIn</a></p>
    <p>Token status: ${token ? 'Saved (tokens.json)' : 'No token saved'}</p>
    <pre>${token ? JSON.stringify(token, null, 2) : ''}</pre>
  `);
});

app.listen(PORT, () => {
  console.log(`App running on http://localhost:${PORT}`);
  console.log(`Open http://localhost:${PORT}/auth/linkedin to start the LinkedIn OAuth flow`);
});
