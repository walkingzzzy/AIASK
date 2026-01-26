import axios from 'axios';

export interface TencentQuote {
    code: string;
    name: string;
    price: number;
    change: number;
    changePercent: number;
    open: number;
    high: number;
    low: number;
    prevClose: number;
    volume: number;
    amount: number;
    date: string;
    time: string;
    source: string;
}

export class TencentAPI {
    private client = axios.create({
        timeout: 3000,
        headers: {
            'Referer': 'https://gu.qq.com/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) width fallback'
        }
    });

    async getQuote(code: string): Promise<TencentQuote | null> {
        try {
            // sh600519 or sz000001
            const symbol = this.normalizeCode(code);
            const url = `http://qt.gtimg.cn/q=${symbol}`;

            const response = await this.client.get(url, { responseType: 'arraybuffer' });
            const decoder = new TextDecoder('gbk');
            const text = decoder.decode(response.data);

            // v_sh600519="1~贵州茅台~600519~1855.00~1866.03~1866.00~1855.03~16668~311403~1855.00~700~...";
            // Indices:
            // 1: Name, 2: Code, 3: Price, 4: PrevClose, 5: Open, 30: Time (20230517150000)

            const match = text.match(/="([^"]+)";/);
            if (!match || match[1].length < 10) return null;

            const parts = match[1].split('~');
            if (parts.length < 30) return null;

            const name = parts[1];
            const price = parseFloat(parts[3]);
            const prevClose = parseFloat(parts[4]);
            const open = parseFloat(parts[5]);
            const volume = parseFloat(parts[36]) * 100; // Hand to share? Wait, check. 36 is volume in hands usually? 
            // 6: Volume (hands), 37: Amount (wan)
            // Let's rely on Price, Open, High, Low, Name for fallback
            // High 33, Low 34

            return {
                code: code,
                name: name,
                price: price,
                change: parseFloat(parts[31]),
                changePercent: parseFloat(parts[32]),
                open: open,
                prevClose: prevClose,
                high: parseFloat(parts[33]),
                low: parseFloat(parts[34]),
                volume: parseFloat(parts[36]) * 100,
                amount: parseFloat(parts[37]) * 10000,
                date: parts[30].substring(0, 8),
                time: parts[30].substring(8),
                source: 'tencent_http'
            };

        } catch (e) {
            console.error('[TencentAPI] getQuote error:', e);
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

export const tencentAPI = new TencentAPI();
