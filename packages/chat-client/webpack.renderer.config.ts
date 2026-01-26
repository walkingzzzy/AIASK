import type { Configuration } from 'webpack';

import { plugins } from './webpack.plugins';

// 渲染进程专用规则，排除 asset-relocator-loader
// 因为 asset-relocator-loader 会注入 __dirname 代码，在 Electron 沙盒环境中不可用
const rendererRules = [
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
  {
    test: /\.css$/,
    use: [{ loader: 'style-loader' }, { loader: 'css-loader' }],
  },
];

export const rendererConfig: Configuration = {
  module: {
    rules: rendererRules,
  },
  plugins,
  resolve: {
    extensions: ['.js', '.ts', '.jsx', '.tsx', '.css'],
  },
  // 使用 source-map 而不是 eval，避免 CSP unsafe-eval 错误
  devtool: 'source-map',
};
