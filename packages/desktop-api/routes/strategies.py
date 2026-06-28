import uuid, json
from datetime import datetime
from fastapi import APIRouter, HTTPException
from database import get_db
from models import ReorderPayload, StrategyCreate, StrategyUpdate

router = APIRouter()

@router.get("")
async def list_strategies(user_id: str):
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM strategies WHERE user_id = ? ORDER BY sort_order ASC, created_at ASC, id ASC",
        (user_id,),
    )
    rows = await cursor.fetchall()
    await db.close()
    result = []
    for row in rows:
        item = dict(row)
        item["stocks"] = json.loads(item["stocks"]) if item["stocks"] else []
        item["config"] = json.loads(item["config"]) if item["config"] else {}
        item["performance"] = json.loads(item["performance"]) if item["performance"] else {}
        result.append(item)
    return result

@router.post("")
async def create_strategy(user_id: str, data: StrategyCreate):
    db = await get_db()
    sid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    cursor = await db.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_sort_order FROM strategies WHERE user_id = ?", (user_id,))
    next_sort_order = int((await cursor.fetchone())["next_sort_order"])
    await db.execute(
        "INSERT INTO strategies (id, name, type, description, stocks, config, status, performance, created_at, updated_at, user_id, sort_order) VALUES (?, ?, ?, ?, ?, ?, 'active', NULL, ?, ?, ?, ?)",
        (
            sid,
            data.name,
            data.type,
            data.description,
            json.dumps(data.stocks) if data.stocks else None,
            json.dumps(data.config) if data.config else None,
            now,
            now,
            user_id,
            next_sort_order,
        ),
    )
    await db.commit()
    await db.close()
    return {
        "id": sid,
        "name": data.name,
        "type": data.type,
        "description": data.description,
        "stocks": data.stocks or [],
        "config": data.config or {},
        "status": "active",
        "performance": {},
        "created_at": now,
        "updated_at": now,
        "user_id": user_id,
        "sort_order": next_sort_order,
    }

@router.patch("/{strategy_id}")
async def update_strategy(user_id: str, strategy_id: str, data: StrategyUpdate):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM strategies WHERE id = ? AND user_id = ?", (strategy_id, user_id))
    if not await cursor.fetchone():
        await db.close()
        raise HTTPException(404)
    updates, values = [], []
    if data.name: updates.append("name = ?"); values.append(data.name)
    if data.type: updates.append("type = ?"); values.append(data.type)
    if data.description is not None: updates.append("description = ?"); values.append(data.description)
    if data.stocks is not None: updates.append("stocks = ?"); values.append(json.dumps(data.stocks))
    if data.config is not None: updates.append("config = ?"); values.append(json.dumps(data.config))
    if data.status: updates.append("status = ?"); values.append(data.status)
    if updates:
        updates.append("updated_at = ?")
        values.append(datetime.utcnow().isoformat())
        values.extend([strategy_id, user_id])
        await db.execute(f"UPDATE strategies SET {', '.join(updates)} WHERE id = ? AND user_id = ?", values)
        await db.commit()
    cursor = await db.execute("SELECT * FROM strategies WHERE id = ? AND user_id = ?", (strategy_id, user_id))
    row = await cursor.fetchone()
    await db.close()
    result = dict(row)
    result["stocks"] = json.loads(result["stocks"]) if result["stocks"] else []
    result["config"] = json.loads(result["config"]) if result["config"] else {}
    result["performance"] = json.loads(result["performance"]) if result["performance"] else {}
    return result


@router.post("/reorder")
async def reorder_strategies(user_id: str, data: ReorderPayload):
    ordered_ids = [str(item).strip() for item in data.ordered_ids if str(item).strip()]
    if not ordered_ids:
        raise HTTPException(400, detail="ordered_ids is required")

    db = await get_db()
    cursor = await db.execute("SELECT id FROM strategies WHERE user_id = ?", (user_id,))
    existing_ids = [str(row["id"]) for row in await cursor.fetchall()]
    await db.close()

    if set(existing_ids) != set(ordered_ids) or len(existing_ids) != len(ordered_ids):
        raise HTTPException(400, detail="ordered_ids must contain the complete strategy id set")

    db = await get_db()
    now = datetime.utcnow().isoformat()
    for index, strategy_id in enumerate(ordered_ids):
        await db.execute(
            "UPDATE strategies SET sort_order = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (index, now, strategy_id, user_id),
        )
    await db.commit()
    await db.close()

    return {"object": "desktop_api.strategy_reorder", "success": True, "data": {"ordered_ids": ordered_ids}}

@router.delete("/{strategy_id}")
async def delete_strategy(user_id: str, strategy_id: str):
    db = await get_db()
    await db.execute("DELETE FROM strategies WHERE id = ? AND user_id = ?", (strategy_id, user_id))
    await db.commit()
    await db.close()
    return {"status": "deleted", "id": strategy_id}
