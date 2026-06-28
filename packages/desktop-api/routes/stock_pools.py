import uuid, json
from datetime import datetime
from fastapi import APIRouter, HTTPException
from database import get_db
from models import AddStockToPool, BatchRemoveStocks, ReorderPayload, StockPoolCreate, StockPoolUpdate

router = APIRouter()

@router.get("")
async def list_pools(user_id: str):
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM stock_pools WHERE user_id = ? ORDER BY sort_order ASC, created_at ASC, id ASC",
        (user_id,),
    )
    rows = await cursor.fetchall()
    await db.close()
    result = []
    for row in rows:
        item = dict(row)
        item["stocks"] = json.loads(item["stocks"]) if item["stocks"] else []
        result.append(item)
    return result

@router.post("")
async def create_pool(user_id: str, data: StockPoolCreate):
    db = await get_db()
    pid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    cursor = await db.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_sort_order FROM stock_pools WHERE user_id = ?", (user_id,))
    next_sort_order = int((await cursor.fetchone())["next_sort_order"])
    await db.execute(
        "INSERT INTO stock_pools (id, name, description, stocks, created_at, updated_at, user_id, sort_order) VALUES (?, ?, ?, '[]', ?, ?, ?, ?)",
        (pid, data.name, data.description, now, now, user_id, next_sort_order),
    )
    await db.commit()
    await db.close()
    return {
        "id": pid,
        "name": data.name,
        "description": data.description,
        "stocks": [],
        "created_at": now,
        "updated_at": now,
        "user_id": user_id,
        "sort_order": next_sort_order,
    }

@router.patch("/{pool_id}")
async def update_pool(user_id: str, pool_id: str, data: StockPoolUpdate):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM stock_pools WHERE id = ? AND user_id = ?", (pool_id, user_id))
    if not await cursor.fetchone():
        await db.close()
        raise HTTPException(404)
    updates, values = [], []
    if data.name: updates.append("name = ?"); values.append(data.name)
    if data.description is not None: updates.append("description = ?"); values.append(data.description)
    if updates:
        updates.append("updated_at = ?")
        values.append(datetime.utcnow().isoformat())
        values.extend([pool_id, user_id])
        await db.execute(f"UPDATE stock_pools SET {', '.join(updates)} WHERE id = ? AND user_id = ?", values)
        await db.commit()
    cursor = await db.execute("SELECT * FROM stock_pools WHERE id = ? AND user_id = ?", (pool_id, user_id))
    row = await cursor.fetchone()
    await db.close()
    result = dict(row)
    result["stocks"] = json.loads(result["stocks"]) if result["stocks"] else []
    return result


@router.post("/reorder")
async def reorder_pools(user_id: str, data: ReorderPayload):
    ordered_ids = [str(item).strip() for item in data.ordered_ids if str(item).strip()]
    if not ordered_ids:
        raise HTTPException(400, detail="ordered_ids is required")

    db = await get_db()
    cursor = await db.execute("SELECT id FROM stock_pools WHERE user_id = ?", (user_id,))
    existing_ids = [str(row["id"]) for row in await cursor.fetchall()]
    await db.close()

    if set(existing_ids) != set(ordered_ids) or len(existing_ids) != len(ordered_ids):
        raise HTTPException(400, detail="ordered_ids must contain the complete stock pool id set")

    db = await get_db()
    now = datetime.utcnow().isoformat()
    for index, pool_id in enumerate(ordered_ids):
        await db.execute(
            "UPDATE stock_pools SET sort_order = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (index, now, pool_id, user_id),
        )
    await db.commit()
    await db.close()

    return {"object": "desktop_api.stock_pool_reorder", "success": True, "data": {"ordered_ids": ordered_ids}}

@router.delete("/{pool_id}")
async def delete_pool(user_id: str, pool_id: str):
    db = await get_db()
    await db.execute("DELETE FROM stock_pools WHERE id = ? AND user_id = ?", (pool_id, user_id))
    await db.commit()
    await db.close()
    return {"status": "deleted", "id": pool_id}

@router.post("/{pool_id}/stocks")
async def add_stock(user_id: str, pool_id: str, data: AddStockToPool):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM stock_pools WHERE id = ? AND user_id = ?", (pool_id, user_id))
    row = await cursor.fetchone()
    if not row:
        await db.close()
        raise HTTPException(404)
    stocks = json.loads(row["stocks"]) if row["stocks"] else []
    if any(s["code"] == data.code for s in stocks):
        await db.close()
        raise HTTPException(400, f"Stock {data.code} already in pool")
    new_stock = {
        "code": data.code,
        "name": data.name,
        "tags": data.tags or [],
        "note": data.note,
        "added_at": datetime.utcnow().isoformat()
    }
    stocks.append(new_stock)
    await db.execute("UPDATE stock_pools SET stocks = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (json.dumps(stocks), datetime.utcnow().isoformat(), pool_id, user_id))
    await db.commit()
    await db.close()
    return {"status": "added", "stock": new_stock}

@router.delete("/{pool_id}/stocks/{stock_code}")
async def remove_stock(user_id: str, pool_id: str, stock_code: str):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM stock_pools WHERE id = ? AND user_id = ?", (pool_id, user_id))
    row = await cursor.fetchone()
    if not row:
        await db.close()
        raise HTTPException(404)
    stocks = json.loads(row["stocks"]) if row["stocks"] else []
    stocks = [s for s in stocks if s["code"] != stock_code]
    await db.execute("UPDATE stock_pools SET stocks = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (json.dumps(stocks), datetime.utcnow().isoformat(), pool_id, user_id))
    await db.commit()
    await db.close()
    return {"status": "removed", "code": stock_code}


@router.post("/{pool_id}/stocks/batch-remove")
async def batch_remove_stocks(user_id: str, pool_id: str, data: BatchRemoveStocks):
    codes = [str(code).strip() for code in data.codes if str(code).strip()]
    if not codes:
        raise HTTPException(400, detail="codes is required")

    db = await get_db()
    cursor = await db.execute("SELECT * FROM stock_pools WHERE id = ? AND user_id = ?", (pool_id, user_id))
    row = await cursor.fetchone()
    if not row:
        await db.close()
        raise HTTPException(404)

    stocks = json.loads(row["stocks"]) if row["stocks"] else []
    stock_map = {str(item.get("code") or ""): item for item in stocks}
    kept = [item for item in stocks if str(item.get("code") or "") not in set(codes)]
    results = []
    for code in codes:
        if code in stock_map:
            results.append({"code": code, "success": True, "removed": True})
        else:
            results.append({"code": code, "success": False, "removed": False, "error": "stock_not_found"})

    await db.execute(
        "UPDATE stock_pools SET stocks = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (json.dumps(kept), datetime.utcnow().isoformat(), pool_id, user_id),
    )
    await db.commit()
    await db.close()
    return {
        "object": "desktop_api.stock_pool_batch_remove",
        "success": True,
        "data": {"pool_id": pool_id, "results": results, "remaining": kept},
    }
