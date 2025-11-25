// helpers/tokenStore.js
// Simple file-backed token store for demo purposes.
// In production, use a secure DB or secret manager.

const fs = require('fs');
const path = require('path');

const TOKENS_FILE = path.join(__dirname, '..', 'tokens.json');

function saveToken(tokenObj) {
  fs.writeFileSync(TOKENS_FILE, JSON.stringify(tokenObj, null, 2), { encoding: 'utf8' });
}

function loadToken() {
  if (!fs.existsSync(TOKENS_FILE)) return null;
  try {
    return JSON.parse(fs.readFileSync(TOKENS_FILE, 'utf8'));
  } catch (e) {
    return null;
  }
}

module.exports = { saveToken, loadToken };
