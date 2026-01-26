import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { callAkshareMcpTool } from '../../adapters/akshare-mcp-client.js';
import { buildManagerHelp } from './manager-help.js';

export const eventManagerTool: ToolDefinition = { name: 'event_manager', description: '事件管理', category: 'insight', inputSchema: managerSchema, dataSource: 'real' };

export const eventManagerHandler: ToolHandler = async (params: any) => {
    const { action, startDate, endDate, eventTypes, code } = params;
    const help = buildManagerHelp(action, {
        actions: ['get_calendar', 'list'],
        description: '事件管理入口（公告/宏观发布记录），action 为空时返回可用动作。',
    });
    if (help) return help;

    const parseDate = (value: string | undefined) => {
        if (!value) return null;
        const raw = String(value).trim();
        if (!raw) return null;
        const normalized = raw.length === 8
            ? `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6)}`
            : raw;
        const date = new Date(normalized);
        return Number.isNaN(date.getTime()) ? null : date;
    };

    const today = new Date();
    const defaultStart = new Date(today);
    defaultStart.setDate(today.getDate() - 7);
    const start = parseDate(startDate) || defaultStart;
    const end = parseDate(endDate) || today;

    if (action === 'get_calendar' || action === 'list') {
        const normalizedTypes = Array.isArray(eventTypes)
            ? eventTypes.map((t: any) => String(t).trim()).filter(Boolean)
            : [];

        const includeMacro = normalizedTypes.length === 0
            || normalizedTypes.some(t => ['macro', '宏观'].includes(t.toLowerCase()));
        const includeNotice = normalizedTypes.length === 0
            || normalizedTypes.some(t => ['notice', '公告', 'announcement'].includes(t.toLowerCase()));

        const noticeTypeMap: Record<string, string> = {
            '重大事项': '重大事项',
            '财务报告': '财务报告',
            '融资公告': '融资公告',
            '风险提示': '风险提示',
            '资产重组': '资产重组',
            '信息变更': '信息变更',
            '持股变动': '持股变动',
            major: '重大事项',
            financial: '财务报告',
            financing: '融资公告',
            risk: '风险提示',
            restructuring: '资产重组',
            change: '信息变更',
            holding: '持股变动',
        };

        const noticeTypes = normalizedTypes
            .map((t: any) => noticeTypeMap[t] || noticeTypeMap[t.toLowerCase()])
            .filter(Boolean);

        const events: Array<Record<string, any>> = [];
        const errors: string[] = [];

        if (includeNotice) {
            const noticeRes = await callAkshareMcpTool<{
                events: Array<{ code: string; name: string; title: string; type: string; date: string; url?: string }>;
            }>('get_stock_notices', {
                start_date: start.toISOString().slice(0, 10),
                end_date: end.toISOString().slice(0, 10),
                types: noticeTypes.length ? noticeTypes : undefined,
                stock_code: code || '',
            });
            if (noticeRes.success && noticeRes.data?.events) {
                noticeRes.data.events.forEach((e: any) => {
                    events.push({
                        date: e.date,
                        type: 'notice',
                        event: e.title || e.type || '公告',
                        code: e.code,
                        name: e.name,
                        source: 'akshare_notice',
                        url: e.url || '',
                    });
                });
            } else if (noticeRes.error) {
                errors.push(`公告数据获取失败: ${noticeRes.error}`);
            }
        }

        if (includeMacro) {
            const macroIndicators = [
                { indicator: 'pmi', name: 'PMI', importance: 'high' },
                { indicator: 'cpi', name: 'CPI', importance: 'high' },
                { indicator: 'ppi', name: 'PPI', importance: 'medium' },
                { indicator: 'gdp', name: 'GDP', importance: 'high' },
                { indicator: 'm2', name: 'M2', importance: 'medium' },
            ];
            const macroRes = await Promise.all(
                macroIndicators.map(async item => ({
                    item,
                    res: await callAkshareMcpTool<{
                        records: Array<{ period: string; value: number | null; publishDate?: string | null }>;
                    }>('get_macro_indicator', { indicator: item.indicator, limit: 24 }),
                }))
            );
            for (const { item, res } of macroRes) {
                if (!res.success || !res.data?.records) {
                    if (res.error) errors.push(`宏观指标 ${item.indicator} 获取失败: ${res.error}`);
                    continue;
                }
                for (const record of res.data.records) {
                    const dateStr = record.publishDate || record.period;
                    if (!dateStr) continue;
                    const date = parseDate(dateStr);
                    if (!date || date < start || date > end) continue;
                    events.push({
                        date: date.toISOString().slice(0, 10),
                        type: 'macro',
                        event: `${item.name} 发布`,
                        value: record.value,
                        importance: item.importance,
                        source: 'akshare_macro',
                    });
                }
            }
        }

        if (!events.length && errors.length) {
            return { success: false, error: errors.join('; ') };
        }

        events.sort((a: any, b: any) => String(b.date).localeCompare(String(a.date)));
        return {
            success: true,
            data: {
                startDate: start.toISOString().slice(0, 10),
                endDate: end.toISOString().slice(0, 10),
                types: normalizedTypes.length ? normalizedTypes : ['macro', 'notice'],
                events,
                total: events.length,
                errors: errors.length ? errors : undefined,
            },
        };
    }

    return { success: false, error: `未知操作: ${action}` };
};
