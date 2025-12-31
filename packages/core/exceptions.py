"""
自定义异常类
提供更清晰的错误信息和分类
"""


class StockAnalysisException(Exception):
    """基础异常类"""
    def __init__(self, message: str, details: str = ""):
        self.message = message
        self.details = details
        super().__init__(self.message)

    def __str__(self):
        if self.details:
            return f"{self.message} - {self.details}"
        return self.message


class DataSourceError(StockAnalysisException):
    """数据源错误"""
    pass


class CacheError(StockAnalysisException):
    """缓存错误"""
    pass


class ValidationError(StockAnalysisException):
    """数据验证错误"""
    pass


class CalculationError(StockAnalysisException):
    """计算错误"""
    pass


class ServiceUnavailableError(StockAnalysisException):
    """服务不可用错误"""
    pass


class InvalidStockCodeError(ValidationError):
    """无效的股票代码"""
    def __init__(self, stock_code: str):
        super().__init__(
            f"无效的股票代码: {stock_code}",
            "请检查股票代码格式是否正确（如：600519、000001）"
        )


class DataNotFoundError(DataSourceError):
    """数据未找到"""
    def __init__(self, data_type: str, identifier: str):
        super().__init__(
            f"未找到{data_type}数据",
            f"标识: {identifier}"
        )


class RateLimitError(ServiceUnavailableError):
    """请求频率限制"""
    def __init__(self, retry_after: int = 60):
        super().__init__(
            "请求过于频繁",
            f"请在{retry_after}秒后重试"
        )
        self.retry_after = retry_after
