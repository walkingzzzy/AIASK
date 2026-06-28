import uuid, json
from datetime import datetime
from fastapi import APIRouter, HTTPException
from database import get_db
from models import ThreadCreate, ThreadUpdate

router = APIRouter()

@router.post("")
async def create_thread(data: ThreadCreate):
    db = await get_db()
    thread_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    await db.execute("INSERT INTO threads (id, title, description, status, message_count, created_at, updated_at, user_id) VALUES (?, ?, ?, 'active', 0, ?, ?, 'default')",
        (thread_id, data.title, data.description, now, now))
    await db.commit()
    await db.close()
    return {"id": thread_id, "title": data.title, "description": data.description, "status": "active", "message_count": 0, "created_at": now, "updated_at": now, "user_id": "default"}

@router.get("")
async def list_threads():
    db = await get_db()
    cursor = await db.execute("SELECT * FROM threads ORDER BY updated_at DESC")
    rows = await cursor.fetchall()
    await db.close()
    return [dict(row) for row in rows]

@router.get("/search")
async def search_threads(keyword: str = ""):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM threads WHERE title LIKE ? OR description LIKE ? ORDER BY updated_at DESC",
        (f"%{keyword}%", f"%{keyword}%"))
    rows = await cursor.fetchall()
    await db.close()
    return [dict(row) for row in rows]

@router.patch("/{thread_id}")
async def update_thread(thread_id: str, data: ThreadUpdate):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM threads WHERE id = ?", (thread_id,))
    if not await cursor.fetchone():
        await db.close()
        raise HTTPException(404, "Thread not found")
    updates, values = [], []
    if data.title: updates.append("title = ?"); values.append(data.title)
    if data.description is not None: updates.append("description = ?"); values.append(data.description)
    if data.status: updates.append("status = ?"); values.append(data.status)
    if updates:
        updates.append("updated_at = ?")
        values.append(datetime.utcnow().isoformat())
        values.append(thread_id)
        await db.execute(f"UPDATE threads SET {', '.join(updates)} WHERE id = ?", values)
        await db.commit()
    cursor = await db.execute("SELECT * FROM threads WHERE id = ?", (thread_id,))
    row = await cursor.fetchone()
    await db.close()
    return dict(row)

@router.post("/{thread_id}/archive")
async def archive_thread(thread_id: str):
    """归档指定线程"""
    db = await get_db()
    cursor = await db.execute("SELECT * FROM threads WHERE id = ?", (thread_id,))
    if not await cursor.fetchone():
        await db.close()
        raise HTTPException(404, "Thread not found")

    await db.execute("UPDATE threads SET status = 'archived', updated_at = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), thread_id))
    await db.commit()

    cursor = await db.execute("SELECT * FROM threads WHERE id = ?", (thread_id,))
    row = await cursor.fetchone()
    await db.close()
    return dict(row)

@router.delete("/{thread_id}")
async def delete_thread(thread_id: str):
    db = await get_db()
    await db.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
    await db.commit()
    await db.close()
    return {"status": "deleted", "id": thread_id}
