import inspect


class _FakeTool:
    def __init__(self, *, name, description, fn, parameters):
        self.name = name
        self.description = description
        self.fn = fn
        self.parameters = parameters
        self.title = None
        self.meta = None


class _ToolManager:
    def __init__(self):
        self._tools = {}


class _RegistryMCP:
    def __init__(self):
        self._tool_manager = _ToolManager()

    def tool(self, **_kwargs):
        def _decorator(fn):
            signature = inspect.signature(fn)
            properties = {}
            required = []
            for name, param in signature.parameters.items():
                annotation = param.annotation
                schema_type = "string"
                if annotation is int:
                    schema_type = "integer"
                elif annotation is float:
                    schema_type = "number"
                elif annotation is bool:
                    schema_type = "boolean"
                properties[name] = {"title": name.replace("_", " ").title(), "type": schema_type}
                if param.default is inspect._empty:
                    required.append(name)

            tool = _FakeTool(
                name=fn.__name__,
                description=(fn.__doc__ or "").strip(),
                fn=fn,
                parameters={
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            )
            self._tool_manager._tools[fn.__name__] = tool
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


def test_get_tool_contract_falls_back_to_runtime_registered_tool():
    from akshare_mcp.tools import search as search_mod

    mcp = _RegistryMCP()

    @mcp.tool()
    async def get_realtime_quote(stock_code: str):
        """获取单只股票实时行情（测试桩）"""
        return {"success": True, "data": {"code": stock_code}}

    get_realtime_quote.__module__ = "akshare_mcp.tools.market.quote"
    search_mod.register(mcp)

    result = mcp.get_tool_contract("get_realtime_quote")

    assert result["success"] is True
    contract = result["data"]["contract"]
    assert contract["name"] == "get_realtime_quote"
    assert contract["required_params"] == ["stock_code"]
    assert contract["category"] == "market"
    assert contract["inferred_from_runtime"] is True
    assert contract["input_schema"]["properties"]["stock_code"]["type"] == "string"
