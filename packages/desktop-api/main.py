from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routes import threads, mcp_servers, skills, strategies, stock_pools, files

app = FastAPI(title="AIASK Desktop API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
async def startup():
    await init_db()

@app.get("/health")
async def health():
    return {"status": "healthy"}

app.include_router(threads.router, prefix="/v1/threads", tags=["threads"])
app.include_router(mcp_servers.router, prefix="/v1/mcp/servers", tags=["mcp"])
app.include_router(skills.router, prefix="/v1/skills", tags=["skills"])
app.include_router(strategies.router, prefix="/v1/users/{user_id}/strategies", tags=["strategies"])
app.include_router(stock_pools.router, prefix="/v1/users/{user_id}/stock-pools", tags=["stock-pools"])
app.include_router(files.router, prefix="/v1/files", tags=["files"])
