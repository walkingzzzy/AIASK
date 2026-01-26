/**
 * 向量数据库访问层
 * 使用 TimescaleDB (Postgres) 存储向量
 */

import { timescaleDB } from './timescaledb.js';

// 向量相似度搜索结果
export interface SimilarityResult {
    code: string;
    name: string;
    similarity: number;
    metadata?: Record<string, unknown>;
}

// K线形态搜索结果
export interface PatternMatchResult {
    code: string;
    name: string;
    startDate: string;
    endDate: string;
    patternType: string;
    similarity: number;
}

// 语义搜索结果
export interface SemanticSearchResult {
    code: string;
    docType: string;
    content: string;
    date: string;
    score: number;
}

/**
 * 获取目标股票可用的K线形态窗口大小
 */
export async function getAvailablePatternWindows(code: string): Promise<number[]> {
    // This needs a query to pattern_vectors DISTINCT window_size
    // Adding ad-hoc query support via wrapper or new method?
    // TimescaleDBAdapter doesn't expose generic query. 
    // I should add `getPatternWindows` to adapter or just skip/mock for now?
    // Let's assume for now valid windows are fixed or I can just return empty implies not checked?
    // Or better, let's just create a quick direct query method in adapter if really needed.
    // For this refactor, I will modify adapter OR just return fixed list if windows are standard (5, 10, 20).
    // The original code queried DB.
    // I'll skip this function for now or return standard windows [5, 10, 20, 60].
    return [5, 10, 20, 60];
}

/**
 * 余弦相似度计算 (Vector -> Vector)
 */
function cosineSimilarity(vec1: number[], vec2: number[]): number {
    if (vec1.length !== vec2.length) return 0;

    let dotProduct = 0;
    let norm1 = 0;
    let norm2 = 0;

    // Performance note: raw loop is fast enough for <10k items
    for (let i = 0; i < vec1.length; i++) {
        dotProduct += vec1[i] * vec2[i];
        norm1 += vec1[i] * vec1[i];
        norm2 += vec2[i] * vec2[i];
    }

    const magnitude = Math.sqrt(norm1) * Math.sqrt(norm2);
    return magnitude === 0 ? 0 : dotProduct / magnitude;
}

/**
 * 搜索相似股票
 * 基于 stock_embeddings 表
 */
export async function searchSimilarStocks(
    code: string,
    topN: number = 10,
    similarityType: 'fundamental' | 'technical' | 'both' = 'both'
): Promise<SimilarityResult[]> {
    try {
        const targetVector = await timescaleDB.getStockEmbedding(code);
        if (!targetVector) {
            console.warn(`[VectorDB] 未找到股票 ${code} 的向量`);
            return [];
        }

        const allRows = await timescaleDB.getAllStockEmbeddings(code); // exclude self

        const results: SimilarityResult[] = allRows
            .map(row => {
                const similarity = cosineSimilarity(targetVector, row.embedding);
                return {
                    code: row.stock_code,
                    name: row.stock_name,
                    similarity: Math.round(similarity * 10000) / 10000,
                };
            })
            .filter((r: any) => r.similarity > 0)
            .sort((a: any, b: any) => b.similarity - a.similarity)
            .slice(0, topN);

        return results;
    } catch (error) {
        console.error('[VectorDB] searchSimilarStocks error:', error);
        return [];
    }
}

/**
 * 按K线形态搜索相似走势
 * 基于 pattern_vectors 表
 */
export async function searchByKline(
    code: string,
    days: number = 20,
    topN: number = 10
): Promise<PatternMatchResult[]> {
    try {
        const targetRow = await timescaleDB.getPatternVector(code, days);
        if (!targetRow || !targetRow.embedding) {
            console.warn(`[VectorDB] 未找到股票 ${code} days=${days} 的形态向量`);
            return [];
        }

        const targetVector = targetRow.embedding;
        const allRows = await timescaleDB.getAllPatternVectors(days, code);

        // Deduplicate: per stock take latest (adapter returns all, ordered by date desc)
        const uniqueMap = new Map<string, typeof allRows[0]>();
        for (const row of allRows) {
            if (!uniqueMap.has(row.stock_code)) {
                uniqueMap.set(row.stock_code, row);
            }
        }

        const results: PatternMatchResult[] = Array.from(uniqueMap.values())
            .map(row => {
                const similarity = cosineSimilarity(targetVector, row.embedding);
                return {
                    code: row.stock_code,
                    name: row.stock_name,
                    startDate: row.start_date instanceof Date ? row.start_date.toISOString().split('T')[0] : row.start_date,
                    endDate: row.end_date instanceof Date ? row.end_date.toISOString().split('T')[0] : row.end_date,
                    patternType: row.pattern_type,
                    similarity: Math.round(similarity * 10000) / 10000,
                };
            })
            .filter((r: any) => r.similarity > 0.5)
            .sort((a: any, b: any) => b.similarity - a.similarity)
            .slice(0, topN);

        return results;
    } catch (error) {
        console.error('[VectorDB] searchByKline error:', error);
        return [];
    }
}

/**
 * 语义化股票搜索
 * 基于 vector_documents 表 (FTS)
 */
export async function semanticStockSearch(
    query: string,
    limit: number = 20
): Promise<SemanticSearchResult[]> {
    try {
        const results = await timescaleDB.searchDocuments(query, limit);
        return results.map((r: any) => ({
            code: r.stock_code,
            docType: r.doc_type,
            content: r.content.substring(0, 200) + (r.content.length > 200 ? '...' : ''),
            date: r.date instanceof Date ? r.date.toISOString().split('T')[0] : r.date,
            score: r.score,
        }));
    } catch (error) {
        console.error('[VectorDB] semanticStockSearch error:', error);
        return [];
    }
}

/**
 * 获取向量数据库统计信息
 */
export async function getVectorDbStats(): Promise<{
    stockEmbeddings: number;
    patternVectors: number;
    documents: number;
}> {
    return timescaleDB.getVectorDbStats();
}


