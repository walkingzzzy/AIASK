"""测试路由以定位Body解析问题"""
from fastapi import FastAPI, Body
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

class ThreadCreate(BaseModel):
    title: str
    description: Optional[str] = None

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/test1")
async def test1(data: ThreadCreate):
    """使用Pydantic模型"""
    return {"method": "pydantic", "title": data.title, "description": data.description}

@app.post("/test2")
async def test2(data: dict):
    """使用dict"""
    return {"method": "dict", "data": data}

@app.post("/test3")
async def test3(title: str = Body(...), description: str = Body(None)):
    """使用Body参数"""
    return {"method": "body", "title": title, "description": description}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8002)
