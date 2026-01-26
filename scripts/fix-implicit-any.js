#!/usr/bin/env node
/**
 * 自动修复隐式 any 类型问题
 * 扫描 TypeScript 文件并添加类型注解
 */

const fs = require('fs');
const path = require('path');

// 需要修复的目录
const DIRS_TO_FIX = [
    'packages/mcp-server-compact/src',
    'packages/mcp-server/src',
];

// 常见的隐式 any 模式
const PATTERNS = [
    {
        // .map(r => r.value) -> .map((r: any) => r.value)
        regex: /\.map\(([a-z])\s*=>/g,
        replacement: '.map(($1: any) =>',
        description: 'map callback parameter'
    },
    {
        // .filter(r => r.value) -> .filter((r: any) => r.value)
        regex: /\.filter\(([a-z])\s*=>/g,
        replacement: '.filter(($1: any) =>',
        description: 'filter callback parameter'
    },
    {
        // .reduce((a, b) => a + b) -> .reduce((a: any, b: any) => a + b)
        regex: /\.reduce\(\(([a-z]),\s*([a-z])\)\s*=>/g,
        replacement: '.reduce(($1: any, $2: any) =>',
        description: 'reduce callback parameters'
    },
    {
        // .sort((a, b) => a - b) -> .sort((a: any, b: any) => a - b)
        regex: /\.sort\(\(([a-z]),\s*([a-z])\)\s*=>/g,
        replacement: '.sort(($1: any, $2: any) =>',
        description: 'sort callback parameters'
    },
    {
        // .forEach(item => ...) -> .forEach((item: any) => ...)
        regex: /\.forEach\(([a-z]+)\s*=>/g,
        replacement: '.forEach(($1: any) =>',
        description: 'forEach callback parameter'
    },
];

function findTsFiles(dir) {
    const files = [];
    
    function walk(currentPath) {
        const entries = fs.readdirSync(currentPath, { withFileTypes: true });
        
        for (const entry of entries) {
            const fullPath = path.join(currentPath, entry.name);
            
            if (entry.isDirectory()) {
                // 跳过 node_modules, dist, .git 等目录
                if (!['node_modules', 'dist', '.git', 'coverage'].includes(entry.name)) {
                    walk(fullPath);
                }
            } else if (entry.isFile() && entry.name.endsWith('.ts') && !entry.name.endsWith('.d.ts')) {
                files.push(fullPath);
            }
        }
    }
    
    walk(dir);
    return files;
}

function fixFile(filePath) {
    let content = fs.readFileSync(filePath, 'utf8');
    let modified = false;
    const changes = [];
    
    for (const pattern of PATTERNS) {
        const matches = content.match(pattern.regex);
        if (matches && matches.length > 0) {
            content = content.replace(pattern.regex, pattern.replacement);
            modified = true;
            changes.push(`${matches.length} ${pattern.description}`);
        }
    }
    
    if (modified) {
        fs.writeFileSync(filePath, content, 'utf8');
        console.log(`✅ Fixed ${filePath}`);
        changes.forEach(change => console.log(`   - ${change}`));
        return 1;
    }
    
    return 0;
}

function main() {
    console.log('🔧 Fixing implicit any types...\n');
    
    let totalFixed = 0;
    
    for (const dir of DIRS_TO_FIX) {
        const fullPath = path.resolve(process.cwd(), dir);
        
        if (!fs.existsSync(fullPath)) {
            console.log(`⚠️  Directory not found: ${dir}`);
            continue;
        }
        
        console.log(`📁 Scanning ${dir}...`);
        const files = findTsFiles(fullPath);
        console.log(`   Found ${files.length} TypeScript files\n`);
        
        for (const file of files) {
            totalFixed += fixFile(file);
        }
    }
    
    console.log(`\n✨ Done! Fixed ${totalFixed} files`);
    console.log('\n⚠️  Note: This script adds "any" types as a quick fix.');
    console.log('   Please review the changes and replace "any" with proper types where possible.');
}

main();
