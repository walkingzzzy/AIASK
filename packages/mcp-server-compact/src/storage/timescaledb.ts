
import pg from 'pg';
import { config } from '../config/index.js';

const { Pool } = pg;

export interface KlineRow {
    code: string;
    date: Date | string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    amount: number;
    turnover?: number;
    change_percent?: number;
}

export interface FinancialsRow {
    code: string;
    report_date: string;
    revenue: number | null;
    net_profit: number | null;
    gross_margin: number | null;
    net_margin: number | null;
    debt_ratio: number | null;
    current_ratio: number | null;
    eps: number | null;
    roe: number | null;
    bvps?: number | null;
    roa?: number | null;
    revenue_growth?: number | null;
    profit_growth?: number | null;
    [key: string]: any;
}

export class TimescaleDBAdapter {
    private pool: pg.Pool;
    private static instance: TimescaleDBAdapter;

    private constructor() {
        this.pool = new Pool({
            user: process.env.DB_USER || 'postgres',
            host: process.env.DB_HOST || 'localhost',
            database: process.env.DB_NAME || 'postgres',
            password: process.env.DB_PASSWORD || 'password',
            port: parseInt(process.env.DB_PORT || '5432', 10),
            max: 20, // Connection pool size
            idleTimeoutMillis: 30000,
            connectionTimeoutMillis: parseInt(process.env.DB_CONNECT_TIMEOUT_MS || '10000', 10),
        });

        this.pool.on('error', (err, client) => {
            console.error('Unexpected error on idle client', err);
        });
    }

    public static getInstance(): TimescaleDBAdapter {
        if (!TimescaleDBAdapter.instance) {
            TimescaleDBAdapter.instance = new TimescaleDBAdapter();
        }
        return TimescaleDBAdapter.instance;
    }

    public async initialize(): Promise<void> {
        const client = await this.pool.connect();
        try {
            // 1. Enable TimescaleDB extension (if not already enabled)
            await client.query('CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;');

            // 2. Create Kline Table
            await client.query(`
                CREATE TABLE IF NOT EXISTS kline_1d (
                    time        TIMESTAMPTZ       NOT NULL,
                    code        TEXT              NOT NULL,
                    open        DOUBLE PRECISION  NOT NULL,
                    high        DOUBLE PRECISION  NOT NULL,
                    low         DOUBLE PRECISION  NOT NULL,
                    close       DOUBLE PRECISION  NOT NULL,
                    volume      BIGINT            NOT NULL,
                    amount      DOUBLE PRECISION,
                    turnover    DOUBLE PRECISION,
                    change_pct  DOUBLE PRECISION,
                    updated_at  TIMESTAMPTZ       DEFAULT NOW(),
                    PRIMARY KEY (time, code)
                );
            `);

            // 3. Convert to Hypertable (Partition by time)
            // Use 'if not exists' logic by checking if it's already a hypertable or catching error
            // Best practice: check \`timescaledb_information.hypertables\`
            const checkHyper = await client.query(`
                SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name = 'kline_1d';
            `);
            if (checkHyper.rowCount === 0) {
                await client.query(`SELECT create_hypertable('kline_1d', 'time');`);
                console.log('Created hypertable: kline_1d');
            }

            // 4. Create Financials Table
            await client.query(`
                CREATE TABLE IF NOT EXISTS financials (
                    code           TEXT        NOT NULL,
                    report_date    DATE        NOT NULL,
                    revenue        DOUBLE PRECISION,
                    net_profit     DOUBLE PRECISION,
                    gross_margin   DOUBLE PRECISION,
                    net_margin     DOUBLE PRECISION,
                    debt_ratio     DOUBLE PRECISION,
                    current_ratio  DOUBLE PRECISION,
                    eps            DOUBLE PRECISION,
                    roe            DOUBLE PRECISION,
                    bvps           DOUBLE PRECISION,
                    roa            DOUBLE PRECISION,
                    revenue_growth DOUBLE PRECISION,
                    profit_growth  DOUBLE PRECISION,
                    updated_at     TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (code, report_date)
                );
            `);

            // Add columns if not exist (migration)
            try {
                await client.query('ALTER TABLE financials ADD COLUMN IF NOT EXISTS revenue_growth DOUBLE PRECISION;');
                await client.query('ALTER TABLE financials ADD COLUMN IF NOT EXISTS profit_growth DOUBLE PRECISION;');
                await client.query('ALTER TABLE financials ADD COLUMN IF NOT EXISTS bvps DOUBLE PRECISION;');
                await client.query('ALTER TABLE financials ADD COLUMN IF NOT EXISTS roa DOUBLE PRECISION;');
            } catch (e) {
                console.warn('Migration columns might already exist:', e);
            }

            // 5. Create Portfolio & App Tables
            await client.query(`
                -- Positions
                CREATE TABLE IF NOT EXISTS positions (
                    id          SERIAL PRIMARY KEY,
                    code        TEXT NOT NULL UNIQUE,
                    name        TEXT NOT NULL,
                    quantity    INTEGER NOT NULL,
                    cost_price  DOUBLE PRECISION NOT NULL,
                    created_at  TIMESTAMPTZ DEFAULT NOW(),
                    updated_at  TIMESTAMPTZ DEFAULT NOW()
                );

                -- Watchlist Groups
                CREATE TABLE IF NOT EXISTS watchlist_groups (
                    id          TEXT PRIMARY KEY,
                    name        TEXT NOT NULL,
                    sort_order  INTEGER DEFAULT 0,
                    created_at  TIMESTAMPTZ DEFAULT NOW()
                );
                INSERT INTO watchlist_groups (id, name, sort_order) 
                VALUES ('default', '默认分组', 0) ON CONFLICT DO NOTHING;

                -- Stocks
                CREATE TABLE IF NOT EXISTS stocks (
                    stock_code TEXT PRIMARY KEY,
                    stock_name TEXT NOT NULL,
                    market     TEXT,
                    sector     TEXT,
                    industry   TEXT,
                    list_date  DATE,
                    kline_sync_attempted TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );

                -- Stock Quotes (Realtime/Valuation)
                CREATE TABLE IF NOT EXISTS stock_quotes (
                    time        TIMESTAMPTZ       NOT NULL,
                    code        TEXT              NOT NULL,
                    name        TEXT,
                    price       DOUBLE PRECISION,
                    change_pct  DOUBLE PRECISION,
                    change_amt  DOUBLE PRECISION,
                    open        DOUBLE PRECISION,
                    high        DOUBLE PRECISION,
                    low         DOUBLE PRECISION,
                    prev_close  DOUBLE PRECISION,
                    volume      BIGINT,
                    amount      DOUBLE PRECISION,
                    pe          DOUBLE PRECISION,
                    pb          DOUBLE PRECISION,
                    mkt_cap     DOUBLE PRECISION,
                    updated_at  TIMESTAMPTZ       DEFAULT NOW()
                );
            `);

            // Hypertable creation: 
            const checkHyperQuotes = await client.query(`
                    SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name = 'stock_quotes';
            `);
            if (checkHyperQuotes.rowCount === 0) {
                await client.query(`SELECT create_hypertable('stock_quotes', 'time'); `);
                console.log('Created hypertable: stock_quotes');
            }

            // Add unique constraint for ON CONFLICT to work (if not exists)
            try {
                await client.query(`
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_stock_quotes_time_code 
                    ON stock_quotes (time, code);
                `);
            } catch (e) {
                // Index might already exist
            }


            // 6. Watchlist & Other Tables
            await client.query(`
                --Watchlist
                CREATE TABLE IF NOT EXISTS watchlist(
                id          SERIAL PRIMARY KEY,
                code        TEXT NOT NULL,
                name        TEXT NOT NULL,
                group_id    TEXT DEFAULT 'default',
                tags        JSONB DEFAULT '[]':: jsonb,
                notes       TEXT,
                added_at    TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(code, group_id)
            );

            --Vector DB Tables
                CREATE TABLE IF NOT EXISTS stock_embeddings(
                stock_code TEXT PRIMARY KEY,
                embedding  REAL[],
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );

                CREATE TABLE IF NOT EXISTS pattern_vectors(
                id           SERIAL PRIMARY KEY,
                stock_code   TEXT,
                window_size  INTEGER,
                embedding    REAL[],
                start_date   DATE,
                end_date     DATE,
                pattern_type TEXT,
                created_at   TIMESTAMPTZ DEFAULT NOW()
            );
                
                CREATE TABLE IF NOT EXISTS vector_documents(
                id           SERIAL PRIMARY KEY,
                stock_code   TEXT,
                doc_type     TEXT,
                content      TEXT,
                date         DATE,
                created_at   TIMESTAMPTZ DEFAULT NOW()
            );
            --FTS Index
                CREATE INDEX IF NOT EXISTS idx_vector_doc_content ON vector_documents USING GIN(to_tsvector('simple', content));
            --Using 'simple' config for Chinese / mixed usually requires specific config or pg_jieba. 
                --Fallback to simple parser or english if not sure.
                
                --Ensure columns exist if migrating
                --(Not adding extensive checks here for brevity in this step)

            --Alerts
                CREATE TABLE IF NOT EXISTS price_alerts(
                id          SERIAL PRIMARY KEY,
                stock_code  TEXT NOT NULL,
                target_price DOUBLE PRECISION,
                condition   TEXT, -- 'gt', 'lt'
                    status      TEXT DEFAULT 'active',
                triggered_at TIMESTAMPTZ,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );
                
                CREATE TABLE IF NOT EXISTS combo_alerts(
                id          SERIAL PRIMARY KEY,
                name        TEXT NOT NULL,
                conditions  TEXT NOT NULL,
                logic       TEXT NOT NULL DEFAULT 'and',
                status      TEXT DEFAULT 'active',
                triggered_at TIMESTAMPTZ,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );

                CREATE TABLE IF NOT EXISTS indicator_alerts(
                id          SERIAL PRIMARY KEY,
                stock_code  TEXT NOT NULL,
                indicator   TEXT NOT NULL,
                condition   TEXT NOT NULL,
                threshold   DOUBLE PRECISION,
                status      TEXT DEFAULT 'active',
                triggered_at TIMESTAMPTZ,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );
            
            CREATE TABLE IF NOT EXISTS limit_alerts (
                id          SERIAL PRIMARY KEY,
                stock_code  TEXT NOT NULL,
                condition   TEXT, 
                status      TEXT DEFAULT 'active',
                triggered_at TIMESTAMPTZ,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS fund_flow_alerts (
                id          SERIAL PRIMARY KEY,
                stock_code  TEXT NOT NULL,
                condition   TEXT, 
                threshold   DOUBLE PRECISION,
                status      TEXT DEFAULT 'active',
                triggered_at TIMESTAMPTZ,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );

            --Data Quality Issues
                CREATE TABLE IF NOT EXISTS data_quality_issues(
                id SERIAL PRIMARY KEY,
                dataset TEXT,
                stock_code TEXT,
                reason TEXT,
                source TEXT,
                payload TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );

            `);

            // 7. Paper Trading Tables
            await client.query(`
                -- Paper Trading Accounts
                CREATE TABLE IF NOT EXISTS paper_accounts (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    initial_capital DOUBLE PRECISION NOT NULL,
                    current_capital DOUBLE PRECISION NOT NULL,
                    total_value DOUBLE PRECISION NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );

                -- Paper Trading Positions
                CREATE TABLE IF NOT EXISTS paper_positions (
                    id SERIAL PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    cost_price DOUBLE PRECISION NOT NULL,
                    current_price DOUBLE PRECISION,
                    market_value DOUBLE PRECISION,
                    profit_rate DOUBLE PRECISION,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(account_id, stock_code)
                );

                -- Paper Trading Trades
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT NOT NULL,
                    trade_type TEXT NOT NULL,
                    price DOUBLE PRECISION NOT NULL,
                    quantity INTEGER NOT NULL,
                    amount DOUBLE PRECISION NOT NULL,
                    commission DOUBLE PRECISION DEFAULT 0,
                    trade_time TIMESTAMPTZ NOT NULL,
                    reason TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_paper_trades_account ON paper_trades(account_id, trade_time DESC);
            `);

            // 8. Backtest Tables
            await client.query(`
                -- Backtest Results
                CREATE TABLE IF NOT EXISTS backtest_results (
                    id TEXT PRIMARY KEY,
                    strategy TEXT NOT NULL,
                    params TEXT,
                    stocks TEXT,
                    start_date DATE NOT NULL,
                    end_date DATE NOT NULL,
                    initial_capital DOUBLE PRECISION NOT NULL,
                    final_capital DOUBLE PRECISION NOT NULL,
                    total_return DOUBLE PRECISION,
                    annual_return DOUBLE PRECISION,
                    max_drawdown DOUBLE PRECISION,
                    sharpe_ratio DOUBLE PRECISION,
                    sortino_ratio DOUBLE PRECISION,
                    win_rate DOUBLE PRECISION,
                    profit_factor DOUBLE PRECISION,
                    avg_win DOUBLE PRECISION,
                    avg_loss DOUBLE PRECISION,
                    expectancy DOUBLE PRECISION,
                    avg_holding_days DOUBLE PRECISION,
                    exposure_rate DOUBLE PRECISION,
                    max_consecutive_loss INTEGER,
                    trades_count INTEGER,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                -- Backtest Trades
                CREATE TABLE IF NOT EXISTS backtest_trades (
                    id TEXT PRIMARY KEY,
                    backtest_id TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    action TEXT NOT NULL,
                    price DOUBLE PRECISION NOT NULL,
                    shares INTEGER NOT NULL,
                    gross_value DOUBLE PRECISION NOT NULL,
                    fee DOUBLE PRECISION DEFAULT 0,
                    slippage DOUBLE PRECISION DEFAULT 0,
                    net_value DOUBLE PRECISION NOT NULL,
                    cash_balance DOUBLE PRECISION NOT NULL,
                    equity DOUBLE PRECISION NOT NULL,
                    trade_date DATE NOT NULL,
                    reason TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                -- Backtest Equity Curve
                CREATE TABLE IF NOT EXISTS backtest_equity (
                    id SERIAL PRIMARY KEY,
                    backtest_id TEXT NOT NULL,
                    date DATE NOT NULL,
                    close DOUBLE PRECISION,
                    cash DOUBLE PRECISION NOT NULL,
                    shares INTEGER,
                    equity DOUBLE PRECISION NOT NULL,
                    daily_return DOUBLE PRECISION,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(backtest_id, date)
                );

                CREATE INDEX IF NOT EXISTS idx_backtest_trades_id ON backtest_trades(backtest_id, trade_date);
                CREATE INDEX IF NOT EXISTS idx_backtest_equity_id ON backtest_equity(backtest_id, date);
            `);

            // 9. Daily PnL Table
            await client.query(`
                -- Daily Portfolio PnL
                CREATE TABLE IF NOT EXISTS daily_pnl (
                    date DATE PRIMARY KEY,
                    total_market_value DOUBLE PRECISION NOT NULL,
                    total_cost DOUBLE PRECISION NOT NULL,
                    total_profit DOUBLE PRECISION NOT NULL,
                    total_profit_rate DOUBLE PRECISION NOT NULL,
                    daily_change DOUBLE PRECISION,
                    daily_change_rate DOUBLE PRECISION,
                    position_count INTEGER NOT NULL,
                    snapshot TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            `);

            // MCP 服务器通过 stdio 通信，不能输出非 JSON 消息
            // 初始化成功，静默处理

        } catch (err) {
            // 初始化失败时抛出错误，但不输出到 stdio（避免 JSON 解析错误）
            throw err;
        } finally {
            client.release();
        }
    }

    public async batchUpsertKline(rows: KlineRow[]): Promise<{ inserted: number; updated: number }> {
        if (rows.length === 0) return { inserted: 0, updated: 0 };

        const client = await this.pool.connect();
        try {
            await client.query('BEGIN');

            const query = `
                INSERT INTO kline_1d(time, code, open, high, low, close, volume, amount, turnover, change_pct)
            SELECT * FROM UNNEST(
                $1:: TIMESTAMPTZ[], $2:: TEXT[], $3:: FLOAT[], $4:: FLOAT[], $5:: FLOAT[],
                $6:: FLOAT[], $7:: BIGINT[], $8:: FLOAT[], $9:: FLOAT[], $10:: FLOAT[]
            )
                ON CONFLICT(time, code) DO UPDATE SET
            open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                amount = EXCLUDED.amount,
                turnover = EXCLUDED.turnover,
                change_pct = EXCLUDED.change_pct,
                updated_at = NOW();
            `;

            // Prepare arrays
            const times = rows.map((r: any) => r.date);
            const codes = rows.map((r: any) => r.code);
            const opens = rows.map((r: any) => r.open);
            const highs = rows.map((r: any) => r.high);
            const lows = rows.map((r: any) => r.low);
            const closes = rows.map((r: any) => r.close);
            const volumes = rows.map((r: any) => BigInt(Math.floor(r.volume))); // Ensure bigint
            const amounts = rows.map((r: any) => r.amount);
            const turnovers = rows.map((r: any) => r.turnover || null);
            const changes = rows.map((r: any) => r.change_percent || null);

            await client.query(query, [
                times, codes, opens, highs, lows, closes, volumes, amounts, turnovers, changes
            ]);

            await client.query('COMMIT');
            return { inserted: rows.length, updated: 0 }; // Approx

        } catch (err) {
            await client.query('ROLLBACK');
            console.error("Batch upsert failed:", err);
            throw err;
        } finally {
            client.release();
        }
    }

    public async upsertFinancials(data: FinancialsRow): Promise<boolean> {
        const query = `
            INSERT INTO financials(
                code, report_date, revenue, net_profit, gross_margin, net_margin,
                debt_ratio, current_ratio, eps, roe, bvps, roa, revenue_growth, profit_growth
            ) VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            ON CONFLICT(code, report_date) DO UPDATE SET
            revenue = EXCLUDED.revenue,
                net_profit = EXCLUDED.net_profit,
                gross_margin = EXCLUDED.gross_margin,
                net_margin = EXCLUDED.net_margin,
                debt_ratio = EXCLUDED.debt_ratio,
                current_ratio = EXCLUDED.current_ratio,
                eps = EXCLUDED.eps,
                roe = EXCLUDED.roe,
                bvps = EXCLUDED.bvps,
                roa = EXCLUDED.roa,
                revenue_growth = EXCLUDED.revenue_growth,
                profit_growth = EXCLUDED.profit_growth,
                updated_at = NOW();
            `;

        try {
            await this.pool.query(query, [
                data.code, data.report_date, data.revenue, data.net_profit,
                data.gross_margin, data.net_margin, data.debt_ratio,
                data.current_ratio, data.eps, data.roe,
                data.bvps ?? null, data.roa ?? null,
                data.revenue_growth, data.profit_growth
            ]);
            return true;
        } catch (err) {
            console.error(`Upsert financials failed for ${data.code}: `, err);
            return false;
        }
    }

    public async batchUpsertFinancials(rows: FinancialsRow[]): Promise<{ inserted: number; failed: number }> {
        if (rows.length === 0) return { inserted: 0, failed: 0 };
        let inserted = 0;
        let failed = 0;

        // Postgres unnest approach for batch is efficient, but let's do simple loop transaction for now for simplicity & error isolation per row if needed?
        // Actually batch with unnest is better.
        // But for financials, data volume is low. Loop is fine.
        const client = await this.pool.connect();
        try {
            await client.query('BEGIN');
            const query = `
                INSERT INTO financials(
                code, report_date, revenue, net_profit, gross_margin, net_margin,
                debt_ratio, current_ratio, eps, roe, bvps, roa, revenue_growth, profit_growth
            ) VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                ON CONFLICT(code, report_date) DO UPDATE SET
            revenue = EXCLUDED.revenue,
                net_profit = EXCLUDED.net_profit,
                gross_margin = EXCLUDED.gross_margin,
                net_margin = EXCLUDED.net_margin,
                debt_ratio = EXCLUDED.debt_ratio,
                current_ratio = EXCLUDED.current_ratio,
                eps = EXCLUDED.eps,
                roe = EXCLUDED.roe,
                bvps = EXCLUDED.bvps,
                roa = EXCLUDED.roa,
                revenue_growth = EXCLUDED.revenue_growth,
                profit_growth = EXCLUDED.profit_growth,
                updated_at = NOW();
            `;

            for (const data of rows) {
                try {
                    await client.query(query, [
                        data.code, data.report_date, data.revenue, data.net_profit,
                        data.gross_margin, data.net_margin, data.debt_ratio,
                        data.current_ratio, data.eps, data.roe,
                        data.bvps ?? null, data.roa ?? null,
                        data.revenue_growth, data.profit_growth
                    ]);
                    inserted++;
                } catch (e) {
                    console.error("Batch upsert financials row failed", e);
                    failed++;
                }
            }
            await client.query('COMMIT');
        } catch (e) {
            await client.query('ROLLBACK');
            console.error("Batch upsert financials transaction failed", e);
            failed = rows.length; // rough estimate
        } finally {
            client.release();
        }
        return { inserted, failed };
    }

    public async getLatestFinancialData(code: string) {
        const res = await this.pool.query('SELECT * FROM financials WHERE code = $1 ORDER BY report_date DESC LIMIT 1', [code]);
        if ((res.rowCount || 0) === 0) return null;
        return res.rows[0]; // Need mapping? FinancialsRow is defined at top, matches DB cols roughly
    }

    public async getFinancialHistory(code: string, limit: number = 20) {
        const res = await this.pool.query('SELECT * FROM financials WHERE code = $1 ORDER BY report_date DESC LIMIT $2', [code, limit]);
        return res.rows;
    }

    public async getStocksNeedingFinancialUpdate(limit: number = 100) {
        // Find stocks with no financials or old financials
        // We can check max(report_date) in financials.
        const res = await this.pool.query(`
            SELECT s.stock_code 
            FROM stocks s
            LEFT JOIN(
                SELECT code, MAX(report_date) as last_report
                FROM financials
                GROUP BY code
            ) f ON s.stock_code = f.code
            WHERE f.last_report IS NULL OR f.last_report < CURRENT_DATE - INTERVAL '90 days'
            LIMIT $1
                `, [limit]);
        return res.rows.map((r: any) => r.stock_code);
    }

    // ========== Valuation/Quotes Methods ==========

    public async getValuationData(code: string) {
        // Get latest
        const res = await this.pool.query('SELECT * FROM stock_quotes WHERE code = $1 ORDER BY time DESC LIMIT 1', [code]);
        if ((res.rowCount || 0) === 0) return null;
        return res.rows[0];
    }

    public async getValuationHistory(code: string, limit: number = 252) {
        const res = await this.pool.query('SELECT * FROM stock_quotes WHERE code = $1 ORDER BY time DESC LIMIT $2', [code, limit]);
        return res.rows;
    }

    public async getBatchValuationData(codes: string[]) {
        if (codes.length === 0) return [];
        // Postgres: SELECT DISTINCT ON (code) * FROM stock_quotes WHERE code = ANY($1) ORDER BY code, time DESC
        const res = await this.pool.query(`
            SELECT DISTINCT ON(code) *
                FROM stock_quotes 
            WHERE code = ANY($1:: text[]) 
            ORDER BY code, time DESC
                `, [codes]);
        return res.rows;
    }

    public async getStocksNeedingQuoteUpdate(hoursOld: number = 24, limit: number = 100) {
        const cutoff = new Date(Date.now() - hoursOld * 60 * 60 * 1000).toISOString();
        // Find stocks with no quote or old quote
        // Using simpler approach: all stocks vs stocks with recent quote
        // Or just: SELECT stock_code FROM stocks s WHERE NOT EXISTS (SELECT 1 FROM stock_quotes q WHERE q.code = s.stock_code AND q.time > $1) LIMIT $2
        const res = await this.pool.query(`
           SELECT stock_code FROM stocks s 
           WHERE NOT EXISTS(
                    SELECT 1 FROM stock_quotes q 
               WHERE q.code = s.stock_code AND q.time > $1
                )
           LIMIT $2
                `, [cutoff, limit]);
        return res.rows.map((r: any) => r.stock_code);
    }

    // ========== Screener Method ==========

    public async screenStocks(criteria: any, limit: number = 50) {
        // Build dynamic query
        // Tables: stocks s, stock_quotes q, financials f (latest)
        // Join q on code + distinct on code (latest quote) -> simplified if assuming stock_quotes has latest? 
        // stock_quotes table structure: (time, code, ...)
        // We need LATEST quote per stock.
        // CTE or lateral join.
        // Also latest financial report.

        let query = `
            WITH latest_quotes AS(
                    SELECT DISTINCT ON(code) *
                FROM stock_quotes
                ORDER BY code, time DESC
                ),
                latest_financials AS(
                    SELECT DISTINCT ON(code) *
                FROM financials
                ORDER BY code, report_date DESC
                )
            SELECT
            s.stock_code as code,
                s.stock_name as name,
                s.sector,
                q.pe as pe,
                q.pb as pb,
                f.roe,
                f.gross_margin,
                f.net_margin,
                f.revenue_growth,
                f.profit_growth,
                q.mkt_cap as market_cap
            FROM stocks s
            LEFT JOIN latest_quotes q ON s.stock_code = q.code
            LEFT JOIN latest_financials f ON s.stock_code = f.code
            WHERE 1 = 1
                `;

        const params: any[] = [];
        let pIdx = 1;

        if (criteria.peMin !== undefined) { query += ` AND q.pe >= $${pIdx++} `; params.push(criteria.peMin); }
        if (criteria.peMax !== undefined) { query += ` AND q.pe <= $${pIdx++} `; params.push(criteria.peMax); }
        if (criteria.pbMin !== undefined) { query += ` AND q.pb >= $${pIdx++} `; params.push(criteria.pbMin); }
        if (criteria.pbMax !== undefined) { query += ` AND q.pb <= $${pIdx++} `; params.push(criteria.pbMax); }
        if (criteria.marketCapMin !== undefined) { query += ` AND q.mkt_cap >= $${pIdx++} `; params.push(criteria.marketCapMin); }
        if (criteria.marketCapMax !== undefined) { query += ` AND q.mkt_cap <= $${pIdx++} `; params.push(criteria.marketCapMax); }

        if (criteria.roeMin !== undefined) { query += ` AND f.roe >= $${pIdx++} `; params.push(criteria.roeMin); }
        if (criteria.roeMax !== undefined) { query += ` AND f.roe <= $${pIdx++} `; params.push(criteria.roeMax); }
        if (criteria.grossMarginMin !== undefined) { query += ` AND f.gross_margin >= $${pIdx++} `; params.push(criteria.grossMarginMin); }
        if (criteria.netMarginMin !== undefined) { query += ` AND f.net_margin >= $${pIdx++} `; params.push(criteria.netMarginMin); }
        if (criteria.revenueGrowthMin !== undefined) { query += ` AND f.revenue_growth >= $${pIdx++} `; params.push(criteria.revenueGrowthMin); }
        if (criteria.profitGrowthMin !== undefined) { query += ` AND f.profit_growth >= $${pIdx++} `; params.push(criteria.profitGrowthMin); }

        if (criteria.sector) { query += ` AND s.sector = $${pIdx++} `; params.push(criteria.sector); }

        // Basic sanity
        query += ` AND q.pe > 0 AND q.pb > 0`;

        query += ` ORDER BY q.mkt_cap DESC LIMIT $${pIdx++} `;
        params.push(limit);

        const res = await this.pool.query(query, params);
        return res.rows;
    }

    public async upsertQuote(quote: any) {
        const time = quote.timestamp ? new Date(quote.timestamp) : new Date();
        await this.pool.query(`
            INSERT INTO stock_quotes(
                    time, code, name, price, change_pct, change_amt, open, high, low, prev_close,
                    volume, amount, pe, pb, mkt_cap
                ) VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            --For hypertable, distinct times are kept.No conflict update usually unless exact time match.
            --If we want to replace "latest" for this second ?
                --Just Insert.History is good.
        `, [
            time, quote.code, quote.name, quote.price, quote.changePercent, quote.changeAmount,
            quote.open, quote.high, quote.low, quote.prevClose, quote.volume, quote.amount,
            quote.pe, quote.pb, quote.marketCap
        ]);
    }

    // ========== Sync Status & Stats ==========

    public async getSyncStatus() {
        // This can be heavy.
        const today = new Date().toISOString().split('T')[0];

        const client = await this.pool.connect();
        try {
            const resStocks = await client.query('SELECT COUNT(*) as cnt FROM stocks');
            const totalStocks = parseInt(resStocks.rows[0].cnt);

            // Quotes updated today (based on time > today start)
            // Using updated_at or time? stock_quotes has `time`.
            const resQuotesToday = await client.query(`
                SELECT COUNT(DISTINCT code) as cnt FROM stock_quotes WHERE time >= $1:: timestamp
                `, [today]);
            const quotesUpdatedToday = parseInt(resQuotesToday.rows[0].cnt);

            // Kline updated today (last bar date = today)
            const resKlineToday = await client.query(`
                SELECT COUNT(DISTINCT code) as cnt FROM kline_1d WHERE time >= $1:: timestamp
                `, [today]);
            const klineUpdatedToday = parseInt(resKlineToday.rows[0].cnt);

            // Last updates
            const resLastQuote = await client.query('SELECT MAX(time) as ts FROM stock_quotes');
            const resLastKline = await client.query('SELECT MAX(time) as ts FROM kline_1d');

            return {
                totalStocks,
                quotesUpdatedToday,
                quotesStale: totalStocks - quotesUpdatedToday,
                klineUpdatedToday,
                klineStale: totalStocks - klineUpdatedToday,
                lastQuoteUpdate: resLastQuote.rows[0].ts,
                lastKlineUpdate: resLastKline.rows[0].ts
            };
        } finally {
            client.release();
        }
    }

    public async getDatabaseStats() {
        const client = await this.pool.connect();
        try {
            const stockCount = parseInt((await client.query('SELECT COUNT(*) as c FROM stocks')).rows[0].c);
            const financialRecords = parseInt((await client.query('SELECT COUNT(*) as c FROM financials')).rows[0].c);
            // kline count
            let dailyBarRecords = 0;
            try {
                const klineRes = await client.query("SELECT COUNT(*) as c FROM kline_1d");
                dailyBarRecords = parseInt(klineRes.rows[0].c);
            } catch { }

            const quoteRecords = parseInt((await client.query('SELECT COUNT(*) as c FROM stock_quotes')).rows[0].c);

            return {
                stockCount,
                financialRecords,
                dailyBarRecords,
                quoteRecords
            };
        } catch (e) {
            console.error("Stats error", e);
            return { stockCount: 0, financialRecords: 0, dailyBarRecords: 0, quoteRecords: 0 };
        } finally {
            client.release();
        }
    }

    // ========== Vector DB Methods ==========

    public async getStockEmbedding(code: string) {
        const res = await this.pool.query('SELECT embedding FROM stock_embeddings WHERE stock_code = $1', [code]);
        if ((res.rowCount || 0) === 0) return null;
        return res.rows[0].embedding; // number[] (real[])
    }

    public async getAllStockEmbeddings(excludeCode?: string) {
        let query = 'SELECT se.stock_code, se.embedding, s.stock_name FROM stock_embeddings se LEFT JOIN stocks s ON se.stock_code = s.stock_code';
        const params: any[] = [];
        if (excludeCode) {
            query += ' WHERE se.stock_code != $1';
            params.push(excludeCode);
        }
        const res = await this.pool.query(query, params);
        return res.rows;
    }

    public async getPatternVector(code: string, windowSize: number) {
        const res = await this.pool.query(`
            SELECT embedding, start_date, end_date, pattern_type 
            FROM pattern_vectors 
            WHERE stock_code = $1 AND window_size = $2 
            ORDER BY end_date DESC LIMIT 1
                `, [code, windowSize]);
        if ((res.rowCount || 0) === 0) return null;
        return res.rows[0];
    }

    public async getAllPatternVectors(windowSize: number, excludeCode?: string) {
        let query = `
            SELECT pv.stock_code, pv.embedding, pv.start_date, pv.end_date, pv.pattern_type, s.stock_name
            FROM pattern_vectors pv
            LEFT JOIN stocks s ON pv.stock_code = s.stock_code
            WHERE pv.window_size = $1
                `;
        const params: any[] = [windowSize];
        if (excludeCode) {
            query += ' AND pv.stock_code != $2';
            params.push(excludeCode);
        }
        // distinct on stock_code to get latest per stock?
        // Logic in adapter: let caller handle filtering or do it here. 
        // Order by end_date desc to help filtering latest
        query += ' ORDER BY pv.end_date DESC';

        const res = await this.pool.query(query, params);
        return res.rows;
    }

    public async searchDocuments(query: string, limit: number = 20) {
        // Full Text Search
        // Using 'websearch_to_tsquery' or 'plainto_tsquery'
        const res = await this.pool.query(`
            SELECT stock_code, doc_type, content, date,
                ts_rank(to_tsvector('simple', content), plainto_tsquery('simple', $1)) as score
            FROM vector_documents
            WHERE to_tsvector('simple', content) @@plainto_tsquery('simple', $1)
            ORDER BY score DESC
            LIMIT $2
                `, [query, limit]);

        if ((res.rowCount || 0) === 0) {
            // Fallback to LIKE
            return await this.searchDocumentsLike(query, limit);
        }
        return res.rows;
    }

    public async searchDocumentsLike(query: string, limit: number = 20) {
        const res = await this.pool.query(`
            SELECT stock_code, doc_type, content, date
            FROM vector_documents
            WHERE content LIKE $1
            ORDER BY date DESC
            LIMIT $2
                `, [` % ${query}% `, limit]);
        return res.rows.map((r: any) => ({ ...r, score: 0 })); // dummy score
    }

    public async getVectorDbStats() {
        const client = await this.pool.connect();
        try {
            const stockEmbeddings = parseInt((await client.query('SELECT COUNT(*) as c FROM stock_embeddings')).rows[0].c);
            const patternVectors = parseInt((await client.query('SELECT COUNT(*) as c FROM pattern_vectors')).rows[0].c);
            const documents = parseInt((await client.query('SELECT COUNT(*) as c FROM vector_documents')).rows[0].c);
            return { stockEmbeddings, patternVectors, documents };
        } finally {
            client.release();
        }
    }

    // ========== Alert Methods ==========

    // --- Price Alerts ---
    public async createPriceAlert(alert: { code: string, targetPrice: number, condition: string }) {
        const res = await this.pool.query(`
            INSERT INTO price_alerts (stock_code, target_price, condition)
            VALUES ($1, $2, $3)
            RETURNING id
        `, [alert.code, alert.targetPrice, alert.condition]);
        return res.rows[0].id;
    }
    public async getPriceAlerts(includeTriggered: boolean = false) {
        let query = 'SELECT * FROM price_alerts';
        if (!includeTriggered) query += " WHERE status = 'active'";
        const res = await this.pool.query(query);
        return res.rows.map((r: any) => ({ ...r, code: r.stock_code, targetPrice: r.target_price, triggeredAt: r.triggered_at, createdAt: r.created_at }));
    }
    public async deletePriceAlert(id: string) {
        const res = await this.pool.query('DELETE FROM price_alerts WHERE id = $1', [id]);
        return (res.rowCount || 0) > 0;
    }

    // --- Limit Alerts ---
    public async createLimitAlert(alert: { code: string, condition: string }) {
        const res = await this.pool.query(`
            INSERT INTO limit_alerts (stock_code, condition)
            VALUES ($1, $2)
            RETURNING id
        `, [alert.code, alert.condition]);
        return res.rows[0].id;
    }
    public async getLimitAlerts(includeTriggered: boolean = false) {
        let query = 'SELECT * FROM limit_alerts';
        if (!includeTriggered) query += " WHERE status = 'active'";
        const res = await this.pool.query(query);
        return res.rows.map((r: any) => ({ ...r, code: r.stock_code, triggeredAt: r.triggered_at, createdAt: r.created_at }));
    }
    public async deleteLimitAlert(id: string) {
        const res = await this.pool.query('DELETE FROM limit_alerts WHERE id = $1', [id]);
        return (res.rowCount || 0) > 0;
    }
    public async triggerLimitAlert(id: string) {
        await this.pool.query("UPDATE limit_alerts SET status = 'triggered', triggered_at = NOW() WHERE id = $1", [id]);
    }

    // --- Fund Flow Alerts ---
    public async createFundFlowAlert(alert: { code: string, condition: string, threshold: number }) {
        const res = await this.pool.query(`
            INSERT INTO fund_flow_alerts (stock_code, condition, threshold)
            VALUES ($1, $2, $3)
            RETURNING id
        `, [alert.code, alert.condition, alert.threshold]);
        return res.rows[0].id;
    }
    public async getFundFlowAlerts(includeTriggered: boolean = false) {
        let query = 'SELECT * FROM fund_flow_alerts';
        if (!includeTriggered) query += " WHERE status = 'active'";
        const res = await this.pool.query(query);
        return res.rows.map((r: any) => ({ ...r, code: r.stock_code, triggeredAt: r.triggered_at, createdAt: r.created_at }));
    }
    public async deleteFundFlowAlert(id: string) {
        const res = await this.pool.query('DELETE FROM fund_flow_alerts WHERE id = $1', [id]);
        return (res.rowCount || 0) > 0;
    }
    public async triggerFundFlowAlert(id: string) {
        await this.pool.query("UPDATE fund_flow_alerts SET status = 'triggered', triggered_at = NOW() WHERE id = $1", [id]);
    }

    // --- Indicator Alerts ---
    public async createIndicatorAlert(alert: { code: string, indicator: string, condition: string, value?: number }) {
        const res = await this.pool.query(`
            INSERT INTO indicator_alerts (stock_code, indicator, condition, threshold)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        `, [alert.code, alert.indicator, alert.condition, alert.value || null]);
        return res.rows[0].id;
    }
    public async getIndicatorAlerts(includeTriggered: boolean = false) {
        let query = 'SELECT * FROM indicator_alerts';
        if (!includeTriggered) query += " WHERE status = 'active'";
        const res = await this.pool.query(query);
        return res.rows.map((r: any) => ({ ...r, code: r.stock_code, triggeredAt: r.triggered_at, createdAt: r.created_at }));
    }
    public async deleteIndicatorAlert(id: string) {
        const res = await this.pool.query('DELETE FROM indicator_alerts WHERE id = $1', [id]);
        return (res.rowCount || 0) > 0;
    }

    // --- Combo Alerts ---
    public async createComboAlert(alert: { name: string, conditions: any[], logic: string }) {
        const res = await this.pool.query(`
            INSERT INTO combo_alerts (name, conditions, logic)
            VALUES ($1, $2, $3)
            RETURNING id
        `, [alert.name, JSON.stringify(alert.conditions), alert.logic]);
        return res.rows[0].id;
    }
    public async getComboAlerts(includeTriggered: boolean = false) {
        let query = 'SELECT * FROM combo_alerts';
        if (!includeTriggered) query += " WHERE status = 'active'";
        const res = await this.pool.query(query);
        return res.rows.map((r: any) => ({ ...r, triggeredAt: r.triggered_at, createdAt: r.created_at }));
    }
    public async deleteComboAlert(id: string) {
        const res = await this.pool.query('DELETE FROM combo_alerts WHERE id = $1', [id]);
        return (res.rowCount || 0) > 0;
    }

    // --- Generic ---
    public async triggerAlert(id: string, type: 'price' | 'indicator' | 'limit' | 'fund_flow' | 'combo' = 'price') {
        const tableMap: any = {
            price: 'price_alerts',
            indicator: 'indicator_alerts',
            limit: 'limit_alerts',
            fund_flow: 'fund_flow_alerts',
            combo: 'combo_alerts'
        };
        const table = tableMap[type] || 'price_alerts';
        await this.pool.query(`UPDATE ${table} SET status = 'triggered', triggered_at = NOW() WHERE id = $1`, [id]);
    }

    // Legacy method for compatibility if needed (returns all alerts)
    public async getAlerts(type: 'combo' | 'indicator' | 'all', status: 'active' | 'triggered' | 'all') {
        const alerts: any[] = [];
        const statusClause = status === 'all' ? '1=1' : "status = $1";
        const params = status === 'all' ? [] : [status];

        if (type === 'all' || type === 'combo') {
            try {
                const res = await this.pool.query(`SELECT * FROM combo_alerts WHERE ${statusClause}`, params);
                res.rows.forEach((r: any) => alerts.push({ ...r, type: 'combo' }));
            } catch (e) { }
        }

        if (type === 'all' || type === 'indicator') {
            try {
                const res = await this.pool.query(`SELECT * FROM indicator_alerts WHERE ${statusClause}`, params);
                res.rows.forEach((r: any) => alerts.push({ ...r, type: 'indicator' }));
            } catch (e) { }
        }
        return alerts;
    }

    // ========== Data Quality ==========

    public async recordDataQualityIssue(issue: { dataset: string, code?: string, reason: string, source?: string, payload?: any }) {
        let payloadStr: string | null = null;
        if (issue.payload !== undefined) {
            try { payloadStr = JSON.stringify(issue.payload); } catch { payloadStr = String(issue.payload); }
        }

        await this.pool.query(`
             INSERT INTO data_quality_issues(dataset, stock_code, reason, source, payload)
            VALUES($1, $2, $3, $4, $5)
                `, [issue.dataset, issue.code || null, issue.reason, issue.source || null, payloadStr]);
    }

    public async getKlineHistory(code: string, start: Date, end: Date): Promise<KlineRow[]> {
        const query = `
            SELECT time as date, code, open, high, low, close, volume:: int as volume, amount, turnover, change_pct as change_percent
            FROM kline_1d
            WHERE code = $1 AND time >= $2 AND time <= $3
            ORDER BY time ASC;
            `;
        const res = await this.pool.query(query, [code, start, end]);
        return res.rows;
    }

    public async close(): Promise<void> {
        await this.pool.end();
    }

    // Generic query method for raw SQL
    public async query(sql: string, params?: any[]): Promise<any> {
        return this.pool.query(sql, params);
    }

    // ========== Stock Info Methods ==========

    public async getStockInfo(code: string) {
        const res = await this.pool.query('SELECT * FROM stocks WHERE stock_code = $1', [code]);
        if ((res.rowCount || 0) === 0) return null;
        const r = res.rows[0];
        return {
            code: r.stock_code,
            name: r.stock_name,
            market: r.market,
            sector: r.sector,
            industry: r.industry,
            listDate: r.list_date
        };
    }

    public async searchStocks(keyword: string, limit: number = 20) {
        const res = await this.pool.query(`
            SELECT * FROM stocks 
            WHERE stock_code LIKE $1 OR stock_name LIKE $1
            LIMIT $2
                `, [` % ${keyword}% `, limit]);
        return res.rows.map((r: any) => ({
            code: r.stock_code,
            name: r.stock_name,
            market: r.market,
            sector: r.sector,
            industry: r.industry,
            listDate: r.list_date
        }));
    }

    public async getStocksBySector(sector: string, limit: number = 50) {
        const res = await this.pool.query('SELECT * FROM stocks WHERE sector = $1 LIMIT $2', [sector, limit]);
        return res.rows.map((r: any) => ({
            code: r.stock_code,
            name: r.stock_name,
            market: r.market,
            sector: r.sector,
            industry: r.industry,
            listDate: r.list_date
        }));
    }



    // ========== Portfolio Methods ==========





    public async getSectorList() {
        const res = await this.pool.query(`
            SELECT DISTINCT sector FROM stocks 
            WHERE sector IS NOT NULL AND sector != ''
            ORDER BY sector
                `);
        return res.rows.map((r: any) => r.sector);
    }


    public async getAllStockCodes(limit: number = 1000) {
        const res = await this.pool.query('SELECT stock_code FROM stocks LIMIT $1', [limit]);
        return res.rows.map((r: any) => r.stock_code);
    }

    public async upsertStock(stock: { code: string, name: string, market?: string, sector?: string, industry?: string, listDate?: string }) {
        await this.pool.query(`
            INSERT INTO stocks(stock_code, stock_name, market, sector, industry, list_date, updated_at)
            VALUES($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT(stock_code) DO UPDATE SET
            stock_name = EXCLUDED.stock_name,
                market = COALESCE(EXCLUDED.market, stocks.market),
                sector = COALESCE(EXCLUDED.sector, stocks.sector),
                industry = COALESCE(EXCLUDED.industry, stocks.industry),
                list_date = COALESCE(EXCLUDED.list_date, stocks.list_date),
                updated_at = NOW()
                    `, [stock.code, stock.name, stock.market, stock.sector, stock.industry, stock.listDate]);
    }

    // ========== Kline Helper Methods ==========

    public async upsertDailyBar(bar: any) {
        await this.pool.query(`
            INSERT INTO kline_1d(
                        code, time, open, high, low, close, volume, amount, turnover, change_pct, updated_at
                    ) VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
            ON CONFLICT(time, code) DO UPDATE SET
            open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                amount = EXCLUDED.amount,
                turnover = EXCLUDED.turnover,
                change_pct = EXCLUDED.change_pct,
                updated_at = NOW()
                    `, [
            bar.code, bar.date, bar.open, bar.high, bar.low, bar.close,
            bar.volume || 0, bar.amount || 0, bar.turnover || null, bar.changePercent || null
        ]);
    }

    public async getStocksNeedingKlineUpdate(limit: number = 100) {
        // Query logic: stock has no kline OR latest kline is old AND sync not attempted recently
        // Need to join stocks and kline_1d... but kline_1d is large. 
        // Optimization: rely on stocks.kline_sync_attempted mostly? 
        // Or aggregate kline_1d by code max(time). 
        // TimescaleDB helps here? 
        // "last(time, time)" agg function from timescaledb or simple max(time)
        // Note: joining large hypertable can be slow.
        // Let's rely on stored sync status if possible, or distinct.
        // For now, simpler query:
        // Use a CTE or just check stocks not updated recently

        const cutoff = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();

        // This is tricky without a separate 'latest_kline_date' col in stocks table.
        // I will assume we can afford a check.
        // Or actually, just Fetch stocks where kline_sync_attempted is null or old.
        // And maybe cross check later.

        const res = await this.pool.query(`
            SELECT stock_code FROM stocks
            WHERE(kline_sync_attempted IS NULL OR kline_sync_attempted < $1)
            LIMIT $2
                `, [cutoff, limit]);
        // Note: this implementation is simpler than SQLite one which checked Max(Data). 
        // To be robust, one should update kline_sync_attempted when kline is saved.
        return res.rows.map((r: any) => r.stock_code);
    }

    public async markKlineSyncAttempted(codes: string[]) {
        if (codes.length === 0) return;
        await this.pool.query(`
            UPDATE stocks SET kline_sync_attempted = NOW() 
            WHERE stock_code = ANY($1:: text[])
                `, [codes]);
    }

    public async getLatestBarDate(code: string) {
        const res = await this.pool.query('SELECT max(time) as d FROM kline_1d WHERE code = $1', [code]);
        if ((res.rowCount || 0) > 0 && res.rows[0].d) return res.rows[0].d;
        return null;
    }


    // ========== Watchlist Methods ==========
    public async getWatchlist(groupId?: string) {
        let query = 'SELECT * FROM watchlist';
        const params: any[] = [];
        if (groupId) {
            query += ' WHERE group_id = $1';
            params.push(groupId);
        }
        const res = await this.pool.query(query, params);
        return res.rows.map((r: any) => ({
            code: r.code,
            name: r.name,
            groupId: r.group_id,
            tags: r.tags || [],
            notes: r.notes,
            addedAt: r.added_at
        }));
    }

    public async addToWatchlist(code: string, name: string, groupId: string = 'default'): Promise<void> {
        await this.pool.query(`
            INSERT INTO watchlist(code, name, group_id) VALUES($1, $2, $3)
            ON CONFLICT(code, group_id) DO NOTHING
                `, [code, name, groupId]);
    }

    public async removeFromWatchlist(code: string, groupId?: string): Promise<boolean> {
        let query = 'DELETE FROM watchlist WHERE code = $1';
        const params: any[] = [code];
        if (groupId) {
            query += ' AND group_id = $2';
            params.push(groupId);
        }
        const res = await this.pool.query(query, params);
        return (res.rowCount || 0) > 0;
    }

    public async getWatchlistGroups() {
        // PG count returns string, need cast
        const res = await this.pool.query(`
            SELECT g.id, g.name, COUNT(w.code):: int as count
            FROM watchlist_groups g
            LEFT JOIN watchlist w ON g.id = w.group_id
            GROUP BY g.id, g.name, g.sort_order
            ORDER BY g.sort_order
                `);
        return res.rows;
    }

    // ========== Portfolio/Position Methods ==========
    public async getPositions() {
        const res = await this.pool.query('SELECT * FROM positions');
        return res.rows.map((r: any) => ({
            id: r.id,
            code: r.code,
            name: r.name,
            quantity: r.quantity,
            costPrice: r.cost_price,
            createdAt: r.created_at
        }));
    }

    public async addPosition(code: string, name: string, quantity: number, costPrice: number) {
        // Weighted average cost calculation on conflict
        await this.pool.query(`
            INSERT INTO positions(code, name, quantity, cost_price)
            VALUES($1, $2, $3, $4)
            ON CONFLICT(code) DO UPDATE SET
            cost_price = (positions.cost_price * positions.quantity + EXCLUDED.cost_price * EXCLUDED.quantity) / (positions.quantity + EXCLUDED.quantity),
                quantity = positions.quantity + EXCLUDED.quantity,
                updated_at = NOW()
                    `, [code, name, quantity, costPrice]);
    }

    public async removePosition(code: string): Promise<boolean> {
        const res = await this.pool.query('DELETE FROM positions WHERE code = $1', [code]);
        return (res.rowCount || 0) > 0;
    }

    // ========== Paper Trading Methods ==========

    public async getPaperAccount(id: string) {
        const res = await this.pool.query('SELECT * FROM paper_accounts WHERE id = $1', [id]);
        return res.rows[0];
    }

    public async createPaperAccount(id: string, name: string, initialCapital: number) {
        await this.pool.query(`
            INSERT INTO paper_accounts(id, name, initial_capital, current_capital, total_value)
            VALUES($1, $2, $3, $3, $3)
                `, [id, name, initialCapital]);
    }

    public async getPaperPositions(accountId: string) {
        const res = await this.pool.query('SELECT * FROM paper_positions WHERE account_id = $1', [accountId]);
        return res.rows.map((r: any) => ({
            ...r,
            costPrice: r.cost_price,
            currentPrice: r.current_price,
            marketValue: r.market_value,
            profitRate: r.profit_rate
        }));
    }

    public async updatePaperPosition(accountId: string, code: string, name: string, quantity: number, costPrice: number, currentPrice: number) {
        // Logic might be complex for full trading, assuming simple update or insert here
        await this.pool.query(`
            INSERT INTO paper_positions(account_id, stock_code, stock_name, quantity, cost_price, current_price, market_value)
            VALUES($1, $2, $3, $4, $5, $6, $4 * $6)
            ON CONFLICT(account_id, stock_code) DO UPDATE SET
            quantity = EXCLUDED.quantity,
                cost_price = EXCLUDED.cost_price,
                current_price = EXCLUDED.current_price,
                market_value = EXCLUDED.quantity * EXCLUDED.current_price,
                updated_at = NOW()
                    `, [accountId, code, name, quantity, costPrice, currentPrice]);
    }
    public async updatePaperPositionPrice(accountId: string, stockCode: string, currentPrice: number) {
        await this.pool.query(`
            UPDATE paper_positions 
            SET current_price = $3, market_value = quantity * $3, updated_at = NOW()
            WHERE account_id = $1 AND stock_code = $2
                `, [accountId, stockCode, currentPrice]);
    }

    public async updatePaperAccount(id: string, currentCapital: number, totalValue: number) {
        await this.pool.query(`
            UPDATE paper_accounts
            SET current_capital = $2, total_value = $3, updated_at = NOW()
            WHERE id = $1
                `, [id, currentCapital, totalValue]);
    }

    public async upsertPaperPosition(accountId: string, stockCode: string, stockName: string, quantity: number, costPrice: number) {
        // Recalculate market value if current price is known, otherwise null? 
        // For simplicity, just insert/update core fields. Market value updates via updatePaperPositionPrice or here if we passed price.
        // Assuming partial update if exists.
        await this.pool.query(`
            INSERT INTO paper_positions(account_id, stock_code, stock_name, quantity, cost_price)
            VALUES($1, $2, $3, $4, $5)
            ON CONFLICT(account_id, stock_code) DO UPDATE SET
            stock_name = EXCLUDED.stock_name,
                quantity = EXCLUDED.quantity,
                cost_price = EXCLUDED.cost_price,
                updated_at = NOW()
                    `, [accountId, stockCode, stockName, quantity, costPrice]);
    }

    public async deletePaperPosition(accountId: string, stockCode: string) {
        await this.pool.query('DELETE FROM paper_positions WHERE account_id = $1 AND stock_code = $2', [accountId, stockCode]);
    }

    public async addPaperTrade(trade: { id: string, accountId: string, stockCode: string, stockName: string, tradeType: string, price: number, quantity: number, amount: number, commission?: number, tradeTime: string, reason?: string }) {
        await this.pool.query(`
            INSERT INTO paper_trades(id, account_id, stock_code, stock_name, trade_type, price, quantity, amount, commission, trade_time, reason)
            VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                `, [trade.id, trade.accountId, trade.stockCode, trade.stockName, trade.tradeType, trade.price, trade.quantity, trade.amount, trade.commission || 0, trade.tradeTime, trade.reason]);
    }

    public async getPaperTrades(accountId: string, limit: number = 50) {
        const res = await this.pool.query('SELECT * FROM paper_trades WHERE account_id = $1 ORDER BY trade_time DESC LIMIT $2', [accountId, limit]);
        return res.rows.map((r: any) => ({
            ...r,
            accountId: r.account_id,
            stockCode: r.stock_code,
            stockName: r.stock_name,
            tradeType: r.trade_type,
            tradeTime: r.trade_time
        }));
    }
    // ========== Daily PnL Methods ==========

    public async getLatestDailyPnL() {
        const res = await this.pool.query('SELECT * FROM daily_pnl ORDER BY date DESC LIMIT 1');
        if ((res.rowCount || 0) === 0) return null;
        const r = res.rows[0];
        return {
            date: r.date,
            totalMarketValue: r.total_market_value,
            totalCost: r.total_cost,
            totalProfit: r.total_profit,
            totalProfitRate: r.total_profit_rate,
            dailyChange: r.daily_change,
            dailyChangeRate: r.daily_change_rate,
            positionCount: r.position_count
        };
    }

    public async saveDailyPnL(data: any) {
        await this.pool.query(`
            INSERT INTO daily_pnl(
                    date, total_market_value, total_cost, total_profit, total_profit_rate,
                    daily_change, daily_change_rate, position_count, snapshot
                ) VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT(date) DO UPDATE SET
            total_market_value = EXCLUDED.total_market_value,
                total_cost = EXCLUDED.total_cost,
                total_profit = EXCLUDED.total_profit,
                total_profit_rate = EXCLUDED.total_profit_rate,
                daily_change = EXCLUDED.daily_change,
                daily_change_rate = EXCLUDED.daily_change_rate,
                position_count = EXCLUDED.position_count,
                snapshot = EXCLUDED.snapshot
                    `, [
            data.date, data.totalMarketValue, data.totalCost, data.totalProfit,
            data.totalProfitRate, data.dailyChange, data.dailyChangeRate,
            data.positionCount, data.snapshot ? JSON.stringify(data.snapshot) : null
        ]);
    }

    public async getDailyPnL(limit: number = 30) {
        const res = await this.pool.query('SELECT * FROM daily_pnl ORDER BY date DESC LIMIT $1', [limit]);
        return res.rows.map((r: any) => ({
            date: r.date,
            totalMarketValue: r.total_market_value,
            totalCost: r.total_cost,
            totalProfit: r.total_profit,
            totalProfitRate: r.total_profit_rate,
            dailyChange: r.daily_change,
            dailyChangeRate: r.daily_change_rate,
            positionCount: r.position_count
        })).reverse();
    }

    public async saveBacktestResult(result: any) {
        await this.pool.query(`
            INSERT INTO backtest_results(
                        id, strategy, params, stocks, start_date, end_date,
                        initial_capital, final_capital, total_return, annual_return,
                        max_drawdown, sharpe_ratio, sortino_ratio, win_rate,
                        profit_factor, avg_win, avg_loss, expectancy,
                        avg_holding_days, exposure_rate, max_consecutive_loss, trades_count
                    ) VALUES(
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22
                    )
                        `, [
            result.id, result.strategy, JSON.stringify(result.params), JSON.stringify(result.stocks),
            result.startDate, result.endDate, result.initialCapital, result.finalCapital,
            result.totalReturn, result.annualReturn, result.maxDrawdown, result.sharpeRatio,
            result.sortinoRatio, result.winRate, result.profitFactor, result.avgWin,
            result.avgLoss, result.expectancy, result.avgHoldingDays, result.exposureRate,
            result.maxConsecutiveLoss, result.tradesCount
        ]);
    }

    public async saveBacktestTrades(backtestId: string, trades: any[]) {
        if (!trades || trades.length === 0) return;
        for (const t of trades) {
            await this.pool.query(`
                INSERT INTO backtest_trades(
                            id, backtest_id, stock_code, action, price, shares, gross_value,
                            fee, slippage, net_value, cash_balance, equity, trade_date, reason
                        ) VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                            `, [t.id, backtestId, t.stockCode, t.action, t.price, t.shares, t.grossValue, t.fee, t.slippage, t.netValue, t.cashBalance, t.equity, t.tradeDate, t.reason]);
        }
    }

    public async saveBacktestEquity(backtestId: string, equity: any[]) {
        if (!equity || equity.length === 0) return;
        for (const e of equity) {
            await this.pool.query(`
                INSERT INTO backtest_equity(
                                backtest_id, date, close, cash, shares, equity, daily_return
                            ) VALUES($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT(backtest_id, date) DO NOTHING
                `, [backtestId, e.date, e.close, e.cash, e.shares, e.equity, e.dailyReturn]);
        }
    }

    public async getBacktestResultById(id: string) {
        const res = await this.pool.query('SELECT * FROM backtest_results WHERE id = $1', [id]);
        if ((res.rowCount || 0) === 0) return null;
        const r = res.rows[0];
        return {
            ...r,
            startDate: r.start_date,
            endDate: r.end_date,
            initialCapital: r.initial_capital,
            finalCapital: r.final_capital,
            totalReturn: r.total_return,
            annualReturn: r.annual_return,
            maxDrawdown: r.max_drawdown,
            sharpeRatio: r.sharpe_ratio,
            sortinoRatio: r.sortino_ratio,
            winRate: r.win_rate,
            profitFactor: r.profit_factor,
            avgWin: r.avg_win,
            avgLoss: r.avg_loss,
            avgHoldingDays: r.avg_holding_days,
            exposureRate: r.exposure_rate,
            maxConsecutiveLoss: r.max_consecutive_loss,
            tradesCount: r.trades_count,
            params: r.params,
            stocks: r.stocks
        };
    }

    public async getBacktestTrades(backtestId: string) {
        const res = await this.pool.query('SELECT * FROM backtest_trades WHERE backtest_id = $1 ORDER BY trade_date ASC', [backtestId]);
        return res.rows.map((r: any) => ({
            ...r,
            stockCode: r.stock_code,
            grossValue: r.gross_value,
            netValue: r.net_value,
            cashBalance: r.cash_balance,
            tradeDate: r.trade_date
        }));
    }

    public async getBacktestEquity(backtestId: string) {
        const res = await this.pool.query('SELECT * FROM backtest_equity WHERE backtest_id = $1 ORDER BY date ASC', [backtestId]);
        return res.rows.map((r: any) => ({
            ...r,
            dailyReturn: r.daily_return
        }));
    }

    public async getBacktestResults(limit: number = 20, strategy?: string) {
        let query = 'SELECT * FROM backtest_results';
        const params: any[] = [];
        if (strategy) {
            query += ' WHERE strategy = $1';
            params.push(strategy);
        }
        query += ' ORDER BY created_at DESC LIMIT $' + (params.length + 1);
        params.push(limit);

        const res = await this.pool.query(query, params);
        return res.rows.map((r: any) => ({
            id: r.id,
            strategy: r.strategy,
            totalReturn: r.total_return,
            maxDrawdown: r.max_drawdown,
            sharpeRatio: r.sharpe_ratio,
            createdAt: r.created_at
        }));
    }


}

export const timescaleDB = TimescaleDBAdapter.getInstance();
