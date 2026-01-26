
const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

const dbPath = path.join(process.env.HOME, 'Library/Application Support/chat-client/user.db');
console.log('Reading database from:', dbPath);

if (!fs.existsSync(dbPath)) {
    console.error('Database file does not exist!');
    process.exit(1);
}

const db = new Database(dbPath);
const row = db.prepare('SELECT value FROM user_config WHERE key = ?').get('user_config');

if (row) {
    console.log('Current Config:', JSON.stringify(JSON.parse(row.value), null, 2));
} else {
    console.log('No config found for key "user_config"');
}
