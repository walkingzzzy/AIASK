from typing import Optional, List
from pydantic import BaseModel

class ThreadCreate(BaseModel):
    title: str
    description: Optional[str] = None

class ThreadUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class MCPServerCreate(BaseModel):
    name: str
    command: str
    args: Optional[List[str]] = None
    env: Optional[dict] = None

class MCPServerUpdate(BaseModel):
    name: Optional[str] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[dict] = None
    enabled: Optional[bool] = None

class SkillCreate(BaseModel):
    name: str
    type: str
    path: str
    config: Optional[dict] = None

class SkillUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    path: Optional[str] = None
    enabled: Optional[bool] = None
    config: Optional[dict] = None

class StrategyCreate(BaseModel):
    name: str
    type: str
    description: Optional[str] = None
    stocks: Optional[List[str]] = None
    config: Optional[dict] = None

class StrategyUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    stocks: Optional[List[str]] = None
    config: Optional[dict] = None
    status: Optional[str] = None


class ReorderPayload(BaseModel):
    ordered_ids: List[str]

class StockPoolCreate(BaseModel):
    name: str
    description: Optional[str] = None

class StockPoolUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class AddStockToPool(BaseModel):
    code: str
    name: str
    tags: Optional[List[str]] = None
    note: Optional[str] = None


class BatchRemoveStocks(BaseModel):
    codes: List[str]
