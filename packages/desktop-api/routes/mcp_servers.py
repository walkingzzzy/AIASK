import json
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException

from database import get_db
from models import MCPServerCreate, MCPServerUpdate

router = APIRouter()


def serialize_server(row) -> dict:
    item = dict(row)
    item["args"] = json.loads(item["args"]) if item["args"] else []
    item["env"] = json.loads(item["env"]) if item["env"] else {}
    item["enabled"] = bool(item.get("enabled"))
    item["status"] = "enabled" if item["enabled"] else "disabled"
    item["transport"] = "stdio"
    return item


@router.get("")
async def list_servers():
    db = await get_db()
    cursor = await db.execute("SELECT * FROM mcp_servers")
    rows = await cursor.fetchall()
    await db.close()
    return [serialize_server(row) for row in rows]


@router.post("")
async def add_server(data: MCPServerCreate):
    db = await get_db()
    sid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    await db.execute(
        "INSERT INTO mcp_servers (id, name, command, args, env, enabled, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
        (sid, data.name, data.command, json.dumps(data.args) if data.args else None, json.dumps(data.env) if data.env else None, now),
    )
    await db.commit()
    await db.close()
    return {
        "id": sid,
        "name": data.name,
        "command": data.command,
        "args": data.args or [],
        "env": data.env or {},
        "enabled": True,
        "status": "enabled",
        "transport": "stdio",
        "created_at": now,
    }


@router.patch("/{server_id}")
async def update_server(server_id: str, data: MCPServerUpdate):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM mcp_servers WHERE id = ?", (server_id,))
    if not await cursor.fetchone():
        await db.close()
        raise HTTPException(404)

    updates, values = [], []
    if data.name:
        updates.append("name = ?")
        values.append(data.name)
    if data.command:
        updates.append("command = ?")
        values.append(data.command)
    if data.args is not None:
        updates.append("args = ?")
        values.append(json.dumps(data.args))
    if data.env is not None:
        updates.append("env = ?")
        values.append(json.dumps(data.env))
    if data.enabled is not None:
        updates.append("enabled = ?")
        values.append(1 if data.enabled else 0)

    if updates:
        values.append(server_id)
        await db.execute(f"UPDATE mcp_servers SET {', '.join(updates)} WHERE id = ?", values)
        await db.commit()

    cursor = await db.execute("SELECT * FROM mcp_servers WHERE id = ?", (server_id,))
    row = await cursor.fetchone()
    await db.close()
    return serialize_server(row)


@router.delete("/{server_id}")
async def delete_server(server_id: str):
    db = await get_db()
    await db.execute("DELETE FROM mcp_servers WHERE id = ?", (server_id,))
    await db.commit()
    await db.close()
    return {"status": "deleted", "id": server_id}
