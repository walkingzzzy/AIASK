/* eslint-disable @typescript-eslint/no-require-imports */
/**
 * Web 版本 Webpack 配置
 */

const path = require('path');
const HtmlWebpackPlugin = require('html-webpack-plugin');

module.exports = {
    mode: process.env.NODE_ENV === 'production' ? 'production' : 'development',
    target: 'web',
    entry: './src/web-entry.tsx',
    output: {
        path: path.resolve(__dirname, 'dist-web'),
        filename: 'bundle.[contenthash].js',
        clean: true,
    },
    module: {
        rules: [
            {
                test: /\.tsx?$/,
                exclude: /node_modules/,
                use: {
                    loader: 'ts-loader',
                    options: {
                        transpileOnly: true,
                    },
                },
            },
            {
                test: /\.css$/,
                use: ['style-loader', 'css-loader'],
            },
        ],
    },
    resolve: {
        extensions: ['.tsx', '.ts', '.js', '.jsx', '.json'],
    },
    plugins: [
        new HtmlWebpackPlugin({
            template: './src/index.web.html',
            filename: 'index.html',
        }),
    ],
    devtool: 'source-map',
    devServer: {
        static: {
            directory: path.join(__dirname, 'dist-web'),
        },
        port: 8080,
        hot: true,
        open: true,
        historyApiFallback: true,
    },
};
