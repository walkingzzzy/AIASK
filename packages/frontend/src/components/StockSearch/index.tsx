/**
 * 股票搜索组件
 * 提供智能股票搜索功能，支持代码和名称搜索
 */
import React, { useState, useCallback } from 'react'
import { AutoComplete, Input } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import { debounce } from 'lodash'

interface StockOption {
  value: string
  label: string
  code: string
  name: string
}

interface StockSearchProps {
  onSelect?: (code: string, name: string) => void
  placeholder?: string
  style?: React.CSSProperties
}

export const StockSearch: React.FC<StockSearchProps> = ({
  onSelect,
  placeholder = '搜索股票代码或名称',
  style
}) => {
  const [options, setOptions] = useState<StockOption[]>([])
  const [loading, setLoading] = useState(false)

  // 搜索股票
  const searchStocks = useCallback(
    debounce(async (searchText: string) => {
      if (!searchText || searchText.length < 2) {
        setOptions([])
        return
      }

      setLoading(true)
      try {
        // 调用API搜索股票
        const response = await fetch(`/api/stocks/search?q=${encodeURIComponent(searchText)}`)
        const data = await response.json()

        const stockOptions: StockOption[] = data.results.map((stock: any) => ({
          value: `${stock.code} ${stock.name}`,
          label: (
            <div className="flex justify-between">
              <span>{stock.name}</span>
              <span className="text-gray-500">{stock.code}</span>
            </div>
          ),
          code: stock.code,
          name: stock.name
        }))

        setOptions(stockOptions)
      } catch (error) {
        console.error('搜索股票失败:', error)
        setOptions([])
      } finally {
        setLoading(false)
      }
    }, 300),
    []
  )

  const handleSearch = (value: string) => {
    searchStocks(value)
  }

  const handleSelect = (value: string, option: any) => {
    if (onSelect) {
      onSelect(option.code, option.name)
    }
  }

  return (
    <AutoComplete
      options={options}
      onSearch={handleSearch}
      onSelect={handleSelect}
      style={{ width: '100%', ...style }}
    >
      <Input
        prefix={<SearchOutlined />}
        placeholder={placeholder}
        loading={loading}
      />
    </AutoComplete>
  )
}

export default StockSearch
