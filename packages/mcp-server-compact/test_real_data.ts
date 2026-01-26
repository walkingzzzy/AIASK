
import { adapterManager } from './src/adapters/index.js';
import dotenv from 'dotenv';
import path from 'path';

// Load .env manualy
dotenv.config({ path: path.resolve(process.cwd(), '.env') });

async function runTest() {
    console.log("Testing AdapterManager...");
    const code = "600519";

    console.log(`\n--- Fetching Realtime Quote for ${code} ---`);
    const quote = await adapterManager.getRealtimeQuote(code);
    if (quote.success && quote.data) {
        console.log("SUCCESS:");
        console.log(`  Name: ${quote.data.name}`);
        console.log(`  Price: ${quote.data.price}`);
        console.log(`  Source: ${quote.source}`);
    } else {
        console.log("FAILURE:", quote.error);
    }

    // Force failure simulation for fallback check is hard without mocking, 
    // but at least we verifying normal flow works.

    console.log(`\n--- Fetching K-Line for ${code} ---`);
    const kline = await adapterManager.getKline(code, '101', 5);
    if (kline.success && kline.data) {
        console.log(`SUCCESS: Got ${kline.data.length} bars`);
        if (kline.data.length > 0) {
            console.log("  Last bar:", kline.data[kline.data.length - 1]);
        }
        console.log(`  Source: ${kline.source}`);
    } else {
        console.log("FAILURE:", kline.error);
    }
}

runTest().catch(console.error);
