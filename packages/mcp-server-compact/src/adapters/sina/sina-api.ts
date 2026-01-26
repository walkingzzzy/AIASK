import axios from 'axios';

export interface SinaQuote {
    code: string;
    name: string;
    open: number;
    // prevClose: number;
    price: number;
    high: number;
    low: number;
    volume: number;
    amount: number;
    date: string;
    time: string;
    source: string;
}

export class SinaAPI {
    private client = axios.create({
        timeout: 3000,
        headers: {
            'Referer': 'https://finance.sina.com.cn/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    });

    async getQuote(code: string): Promise<SinaQuote | null> {
        try {
            // sh600519 or sz000001
            const symbol = this.normalizeCode(code);
            const url = `http://hq.sinajs.cn/list=${symbol}`;

            const response = await this.client.get(url, { responseType: 'arraybuffer' });
            // Sina uses GBK
            const decoder = new TextDecoder('gbk');
            const text = decoder.decode(response.data);

            // var hq_str_sh600519="贵州茅台,1866.000,1866.030,1855.000,1878.880,1850.000,1855.010,1855.030,1666870,3114032156.000,100,1855.010,700,1854.990,300,1854.910,200,1854.900,100,1854.890,200,1855.030,400,1855.090,300,1855.100,500,1855.300,200,1855.350,2024-05-17,15:00:00,00,";
            const match = text.match(/="([^"]+)";/);
            if (!match || match[1].length < 10) {
                return null;
            }

            const parts = match[1].split(',');
            // 0: name, 1: open, 2: prev_close, 3: price, 4: high, 5: low, 8: volume (share), 9: amount (yuan)
            // 30: date, 31: time

            if (parts.length < 10) return null;

            return {
                code: code,
                name: parts[0],
                open: parseFloat(parts[1]),
                // prevClose: parseFloat(parts[2]),
                price: parseFloat(parts[3]),
                high: parseFloat(parts[4]),
                low: parseFloat(parts[5]),
                volume: parseFloat(parts[8]),
                amount: parseFloat(parts[9]),
                date: parts[30],
                time: parts[31],
                source: 'sina_http'
            };

        } catch (e) {
            console.error('[SinaAPI] getQuote error:', e);
            return null;
        }
    }

    private normalizeCode(code: string): string {
        if (/^\d{6}$/.test(code)) {
            return (code.startsWith('6') ? 'sh' : 'sz') + code;
        }
        return code.toLowerCase();
    }
}

export const sinaAPI = new SinaAPI();
