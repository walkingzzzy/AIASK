"""
FastAPI后端服务模块
"""
from .main import app

__all__ = ['app']


def start_server(host: str = "0.0.0.0", port: int = 8000):
    """启动服务器"""
    import uvicorn
    uvicorn.run(app, host=host, port=port)
