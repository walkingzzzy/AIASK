/**
 * 对话历史存储
 */

import Database from 'better-sqlite3';
import { app } from 'electron';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';

let db: Database.Database | null = null;

/**
 * 获取数据库路径
 */
function getDBPath(): string {
  const userDataPath = app.getPath('userData');
  return path.join(userDataPath, 'chat.db');
}

/**
 * 初始化数据库
 */
export function initChatStore(): Database.Database {
  if (db) return db;

  const dbPath = getDBPath();
  console.log('[ChatStore] Database path:', dbPath);

  db = new Database(dbPath);

  // 创建表
  db.exec(`
    CREATE TABLE IF NOT EXISTS chat_sessions (
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      summary TEXT,
      tags TEXT,
      created_at INTEGER NOT NULL,
      updated_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS chat_messages (
      id TEXT PRIMARY KEY,
      session_id TEXT NOT NULL,
      role TEXT NOT NULL,
      content TEXT NOT NULL,
      tool_calls TEXT,
      metadata TEXT,
      created_at INTEGER NOT NULL,
      FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
    );

    CREATE INDEX IF NOT EXISTS idx_messages_session ON chat_messages(session_id);
    CREATE INDEX IF NOT EXISTS idx_messages_created ON chat_messages(created_at);
  `);

  console.log('[ChatStore] Database initialized');
  return db;
}

/**
 * 创建新会话
 */
export function createSession(title: string = '新对话'): { id: string; title: string; createdAt: number } {
  if (!db) initChatStore();

  const id = uuidv4();
  const now = Date.now();

  db!.prepare(`
    INSERT INTO chat_sessions (id, title, created_at, updated_at)
    VALUES (?, ?, ?, ?)
  `).run(id, title, now, now);

  return { id, title, createdAt: now };
}

/**
 * 获取所有会话
 */
export function getSessions(): unknown[] {
  if (!db) initChatStore();

  return db!.prepare(`
    SELECT id, title, summary, tags, created_at as createdAt, updated_at as updatedAt
    FROM chat_sessions
    ORDER BY updated_at DESC
  `).all();
}

/**
 * 保存消息
 */
export function saveMessage(
  sessionId: string,
  role: 'user' | 'assistant' | 'system' | 'tool',
  content: string,
  toolCalls?: unknown,
  metadata?: unknown
): string {
  if (!db) initChatStore();

  const id = uuidv4();
  const now = Date.now();

  db!.prepare(`
    INSERT INTO chat_messages (id, session_id, role, content, tool_calls, metadata, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `).run(
    id,
    sessionId,
    role,
    content,
    toolCalls ? JSON.stringify(toolCalls) : null,
    metadata ? JSON.stringify(metadata) : null,
    now
  );

  // 更新会话时间
  db!.prepare(`UPDATE chat_sessions SET updated_at = ? WHERE id = ?`).run(now, sessionId);

  return id;
}

/**
 * 获取会话消息
 */
export function getMessages(sessionId: string): unknown[] {
  if (!db) initChatStore();

  return db!.prepare(`
    SELECT id, role, content, tool_calls as toolCalls, metadata, created_at as createdAt
    FROM chat_messages
    WHERE session_id = ?
    ORDER BY created_at ASC
  `).all(sessionId);
}

/**
 * 更新会话标题
 */
export function updateSessionTitle(sessionId: string, title: string): void {
  if (!db) initChatStore();

  db!.prepare(`UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?`)
    .run(title, Date.now(), sessionId);
}

/**
 * 删除会话及其消息
 */
export function deleteSession(sessionId: string): void {
  if (!db) initChatStore();

  db!.prepare(`DELETE FROM chat_messages WHERE session_id = ?`).run(sessionId);
  db!.prepare(`DELETE FROM chat_sessions WHERE id = ?`).run(sessionId);
}

/**
 * 搜索会话和消息
 */
export function searchMessages(query: string): unknown[] {
  if (!db) initChatStore();

  return db!.prepare(`
        SELECT m.id, m.session_id, m.role, m.content, m.created_at as createdAt,
               s.title as sessionTitle
        FROM chat_messages m
        JOIN chat_sessions s ON m.session_id = s.id
        WHERE m.content LIKE ?
        ORDER BY m.created_at DESC
        LIMIT 50
    `).all(`%${query}%`);
}

/**
 * 关闭数据库
 */
export function closeChatStore(): void {
  if (db) {
    db.close();
    db = null;
    console.log('[ChatStore] Database closed');
  }
}

