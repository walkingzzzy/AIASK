/**
 * 通用数据表
 */

import React, { useMemo } from 'react';

interface DataTableProps {
    title?: string;
    data: unknown;
}

const formatCell = (value: unknown): string => {
    if (value === null || value === undefined) return '--';
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
};

const extractRows = (data: unknown): Array<Record<string, unknown>> => {
    if (Array.isArray(data)) {
        if (data.length === 0) return [];
        const first = data[0];
        if (!first || typeof first !== 'object') {
            return data.map(item => ({ value: item }));
        }
        return data as Array<Record<string, unknown>>;
    }

    if (data && typeof data === 'object') {
        const payload = data as Record<string, unknown>;
        if (Array.isArray(payload.stocks)) return payload.stocks as Array<Record<string, unknown>>;
        if (Array.isArray(payload.positions)) return payload.positions as Array<Record<string, unknown>>;
        if (Array.isArray(payload.sectors)) return payload.sectors as Array<Record<string, unknown>>;
        if (Array.isArray(payload.daily)) return payload.daily as Array<Record<string, unknown>>;
        if (Array.isArray(payload.decisions)) return payload.decisions as Array<Record<string, unknown>>;
        if (Array.isArray(payload.list)) return payload.list as Array<Record<string, unknown>>;
        if (Array.isArray(payload.data)) return payload.data as Array<Record<string, unknown>>;

        return Object.entries(payload).map(([key, value]) => ({ key, value }));
    }

    return [];
};

const DataTable: React.FC<DataTableProps> = ({ title, data }) => {
    const rows = useMemo(() => extractRows(data), [data]);

    if (rows.length === 0) {
        return (
            <div className="visualization data-table empty">
                {title && <div className="visualization-title">{title}</div>}
                <div className="data-empty">暂无数据</div>
            </div>
        );
    }

    const columns = Object.keys(rows[0]).slice(0, 8);

    return (
        <div className="visualization data-table">
            {title && <div className="visualization-title">{title}</div>}
            <div className="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            {columns.map(col => (
                                <th key={col}>{col}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((row, rowIndex) => (
                            <tr key={rowIndex}>
                                {columns.map(col => (
                                    <td key={col}>{formatCell(row[col])}</td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default DataTable;
