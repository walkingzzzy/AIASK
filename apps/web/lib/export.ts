/** Export an array of objects as a CSV file download */
export function exportCSV(rows: Record<string, unknown>[], filename = 'export.csv') {
  if (!rows.length) return;
  const keys = Object.keys(rows[0]);
  const header = keys.join(',');
  const body = rows.map((r) => keys.map((k) => {
    const v = r[k];
    if (v == null) return '';
    const s = String(v);
    return s.includes(',') || s.includes('"') || s.includes('\n') ? `"${s.replace(/"/g, '""')}"` : s;
  }).join(',')).join('\n');
  const csv = '\uFEFF' + header + '\n' + body; // BOM for Excel CJK support
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
