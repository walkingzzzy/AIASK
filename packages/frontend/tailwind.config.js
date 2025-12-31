/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 股票涨跌颜色（中国市场：红涨绿跌）
        'stock-up': '#ef4444',      // 红色-上涨
        'stock-down': '#22c55e',    // 绿色-下跌
        'stock-flat': '#6b7280',    // 灰色-平盘
        // 品牌色
        'primary': '#1677ff',
        'secondary': '#722ed1',
      },
    },
  },
  plugins: [],
  // 与Ant Design兼容
  corePlugins: {
    preflight: false,
  },
}
