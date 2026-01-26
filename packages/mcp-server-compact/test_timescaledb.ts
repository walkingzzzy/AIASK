
import { timescaleDB } from './src/storage/timescaledb.js';

async function testConnection() {
    console.log("Initializing TimescaleDB...");
    try {
        await timescaleDB.initialize();
        console.log("Initialization successful.");

        console.log("Inserting dummy K-line data...");
        const result = await timescaleDB.batchUpsertKline([
            {
                code: "TEST001",
                date: new Date(),
                open: 10.0,
                high: 10.5,
                low: 9.8,
                close: 10.2,
                volume: 1000,
                amount: 10000,
                turnover: 1.5,
                change_percent: 2.0
            }
        ]);
        console.log("Insert result:", result);

        console.log("Querying data...");
        const history = await timescaleDB.getKlineHistory("TEST001", new Date(Date.now() - 86400000), new Date());
        console.log("Query result:", history);

    } catch (error) {
        console.error("Test failed:", error);
    } finally {
        await timescaleDB.close();
    }
}

testConnection();
