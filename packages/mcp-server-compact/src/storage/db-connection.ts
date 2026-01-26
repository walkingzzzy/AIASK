
import { timescaleDB } from './timescaledb.js';

let isInitialized = false;

export async function initDatabase() {
    if (isInitialized) return;

    console.log('[DB] Connecting to TimescaleDB...');
    try {
        await timescaleDB.initialize();
        isInitialized = true;
        console.log('[DB] TimescaleDB Connection Verified');
    } catch (error) {
        console.error('[DB] Failed to connect:', error);
        // Do not exit process, just log error, maybe retry later
    }
}

export async function closeDatabase() {
    if (!isInitialized) return;
    await timescaleDB.close();
    isInitialized = false;
    console.log('[DB] Connection closed');
}
