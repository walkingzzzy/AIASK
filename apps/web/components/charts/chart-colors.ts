/**
 * T-022: Chart color constants with dark mode awareness.
 * Provides both static colors and a getColors() function
 * that reads the current theme from the DOM.
 */

/** Static chart colors (always available, Chinese market convention) */
export const COLORS = {
  primary: '#1a73e8',
  success: '#10b981',
  danger: '#ef4444',
  warning: '#f59e0b',
  info: '#3b82f6',
  muted: '#9ca3af',

  // Stock-specific (Chinese: red=up, green=down)
  up: '#ef4444',
  down: '#10b981',
  flat: '#9ca3af',

  // Chart series palette
  series: ['#1a73e8', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'],
};

/** Dark mode aware colors */
const DARK_OVERRIDES = {
  primary: '#5b9cf6',
  success: '#34d399',
  danger: '#f87171',
  warning: '#fbbf24',
  info: '#60a5fa',
  muted: '#6b7280',
  up: '#f87171',
  down: '#34d399',
  flat: '#6b7280',
  series: ['#5b9cf6', '#f87171', '#34d399', '#fbbf24', '#a78bfa', '#f472b6', '#22d3ee', '#a3e635'],
};

/** Get whether dark mode is active */
export function isDarkMode(): boolean {
  if (typeof window === 'undefined') return false;
  return document.documentElement.classList.contains('dark') ||
    (!document.documentElement.classList.contains('light') &&
      window.matchMedia('(prefers-color-scheme: dark)').matches);
}

/** Get theme-aware colors */
export function getColors(): typeof COLORS {
  if (isDarkMode()) {
    return { ...COLORS, ...DARK_OVERRIDES };
  }
  return COLORS;
}

/** ECharts theme config for dark mode */
export function getChartTheme() {
  const dark = isDarkMode();
  return {
    backgroundColor: 'transparent',
    textStyle: { color: dark ? '#e0e0e0' : '#333' },
    legend: { textStyle: { color: dark ? '#aaa' : '#666' } },
    tooltip: {
      backgroundColor: dark ? 'rgba(30,30,30,0.9)' : 'rgba(255,255,255,0.95)',
      borderColor: dark ? '#444' : '#ddd',
      textStyle: { color: dark ? '#e0e0e0' : '#333' },
    },
    xAxis: {
      axisLine: { lineStyle: { color: dark ? '#444' : '#ddd' } },
      axisLabel: { color: dark ? '#aaa' : '#666' },
      splitLine: { lineStyle: { color: dark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)' } },
    },
    yAxis: {
      axisLine: { lineStyle: { color: dark ? '#444' : '#ddd' } },
      axisLabel: { color: dark ? '#aaa' : '#666' },
      splitLine: { lineStyle: { color: dark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)' } },
    },
  };
}

export const CHART_GRID = { left: 50, right: 20, top: 30, bottom: 40 };
