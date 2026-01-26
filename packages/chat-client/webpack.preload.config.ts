import type { Configuration } from 'webpack';

// Preload 脚本专用的简化规则，不包含 asset-relocator-loader
// 因为 asset-relocator-loader 会注入 __dirname 代码，在 Electron 沙盒环境中不可用
const preloadRules = [
    {
        test: /\.tsx?$/,
        exclude: /(node_modules|\.webpack)/,
        use: {
            loader: 'ts-loader',
            options: {
                transpileOnly: true,
            },
        },
    },
];

export const preloadConfig: Configuration = {
    module: {
        rules: preloadRules,
    },
    resolve: {
        extensions: ['.js', '.ts', '.jsx', '.tsx', '.json'],
    },
    // 关键: 设置 target 为 electron-preload
    target: 'electron-preload',
    // 不要对 Node.js 内置模块进行打包
    externals: {
        electron: 'commonjs electron',
    },
};
