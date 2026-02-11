# 创建自定义板块 create_sector

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h139a4ckchkk/mindoc-1h10rrkuj1drs.html
> 抓取时间: 2026-02-03

## 函数说明

在通达信客户端中创建自定义板块。

```python
create_sector(block_code: str = '',
              block_name: str = ''):
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| block_code | Y | str | 自定义板块简称 |
| block_name | Y | str | 自定义板块名称 |

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)
create_ptr = tq.create_sector(block_code='CSBK2', block_name='测试板块2')
print(create_ptr)
```

## 返回数据样本

```python
{
   "Error": "创建CSBK2板块成功",
   "ErrorId": "0",
   "run_id": "1"
}
```

