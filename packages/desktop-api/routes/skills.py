import json
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException

from database import get_db
from models import SkillCreate, SkillUpdate

router = APIRouter()


def serialize_skill(row) -> dict:
    item = dict(row)
    item["config"] = json.loads(item["config"]) if item["config"] else {}
    item["enabled"] = bool(item.get("enabled"))
    item["status"] = "enabled" if item["enabled"] else "disabled"
    return item


@router.get("")
async def list_skills():
    db = await get_db()
    cursor = await db.execute("SELECT * FROM skills")
    rows = await cursor.fetchall()
    await db.close()
    return [serialize_skill(row) for row in rows]


@router.post("")
async def add_skill(data: SkillCreate):
    db = await get_db()
    sid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    await db.execute(
        "INSERT INTO skills (id, name, type, path, enabled, config, created_at) VALUES (?, ?, ?, ?, 1, ?, ?)",
        (sid, data.name, data.type, data.path, json.dumps(data.config) if data.config else None, now),
    )
    await db.commit()
    await db.close()
    return {
        "id": sid,
        "name": data.name,
        "type": data.type,
        "path": data.path,
        "enabled": True,
        "status": "enabled",
        "config": data.config or {},
        "created_at": now,
    }


@router.patch("/{skill_id}")
async def update_skill(skill_id: str, data: SkillUpdate):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM skills WHERE id = ?", (skill_id,))
    if not await cursor.fetchone():
        await db.close()
        raise HTTPException(404)

    updates, values = [], []
    if data.name:
        updates.append("name = ?")
        values.append(data.name)
    if data.type:
        updates.append("type = ?")
        values.append(data.type)
    if data.path:
        updates.append("path = ?")
        values.append(data.path)
    if data.enabled is not None:
        updates.append("enabled = ?")
        values.append(1 if data.enabled else 0)
    if data.config is not None:
        updates.append("config = ?")
        values.append(json.dumps(data.config))

    if updates:
        values.append(skill_id)
        await db.execute(f"UPDATE skills SET {', '.join(updates)} WHERE id = ?", values)
        await db.commit()

    cursor = await db.execute("SELECT * FROM skills WHERE id = ?", (skill_id,))
    row = await cursor.fetchone()
    await db.close()
    return serialize_skill(row)


@router.delete("/{skill_id}")
async def delete_skill(skill_id: str):
    db = await get_db()
    await db.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
    await db.commit()
    await db.close()
    return {"status": "deleted", "id": skill_id}
