import React, { useState, useEffect } from 'react';
import { Card, Table, Tag, Statistic, Row, Col, Tabs, message } from 'antd';
import { RiseOutlined, FallOutlined, ThunderboltOutlined } from '@ant-design/icons';
import axios from 'axios';

const { TabPane } = Tabs;

interface AuctionStock {
  stock_code: string;
  stock_name: string;
  price: number;
  change_pct: number;
  volume: number;
  volume_ratio: number;
  big_order_amount?: number;
  amount?: number;
}

interface AuctionData {
  change_ranking: AuctionStock[];
  volume_ranking: AuctionStock[];
  abnormal_stocks: AuctionStock[];
}

const CallAuction: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [auctionData, setAuctionData] = useState<AuctionData | null>(null);
  const [refreshTime, setRefreshTime] = useState<string>('');

  useEffect(() => {
    fetchAuctionData();
    // 每30秒自动刷新
    const interval = setInterval(fetchAuctionData, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchAuctionData = async () => {
    setLoading(true);
    try {
      const response = await axios.get('http://127.0.0.1:8000/api/call-auction/ranking', {
        params: { top_n: 50 }
      });

      if (response.data.success) {
        setAuctionData(response.data.data);
        setRefreshTime(new Date().toLocaleTimeString());
      }
    } catch (error) {
      message.error('获取竞价数据失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const changeColumns = [
    {
      title: '排名',
      key: 'rank',
      width: 60,
      render: (_: any, __: any, index: number) => index + 1,
    },
    {
      title: '股票代码',
      dataIndex: 'stock_code',
      key: 'stock_code',
      width: 100,
    },
    {
      title: '股票名称',
      dataIndex: 'stock_name',
      key: 'stock_name',
      width: 120,
    },
    {
      title: '竞价价格',
      dataIndex: 'price',
      key: 'price',
      width: 100,
      render: (price: number) => `¥${price.toFixed(2)}`,
    },
    {
      title: '涨跌幅',
      dataIndex: 'change_pct',
      key: 'change_pct',
      width: 100,
      render: (change: number) => (
        <Tag color={change > 0 ? 'red' : change < 0 ? 'green' : 'default'}>
          {change > 0 ? '+' : ''}{change.toFixed(2)}%
        </Tag>
      ),
    },
    {
      title: '竞价量',
      dataIndex: 'volume',
      key: 'volume',
      width: 100,
      render: (vol: number) => (vol / 10000).toFixed(2) + '万',
    },
    {
      title: '量比',
      dataIndex: 'volume_ratio',
      key: 'volume_ratio',
      width: 80,
      render: (ratio: number) => ratio.toFixed(2),
    },
  ];

  const abnormalColumns = [
    ...changeColumns,
    {
      title: '大单金额',
      dataIndex: 'big_order_amount',
      key: 'big_order_amount',
      width: 120,
      render: (amount: number) => amount ? `¥${(amount / 100000000).toFixed(2)}亿` : '-',
    },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="异动股票"
              value={auctionData?.abnormal_stocks.length || 0}
              prefix={<ThunderboltOutlined />}
              suffix="只"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="涨停预期"
              value={auctionData?.change_ranking.filter(s => s.change_pct > 9).length || 0}
              prefix={<RiseOutlined />}
              suffix="只"
              valueStyle={{ color: '#cf1322' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="跌停预期"
              value={auctionData?.change_ranking.filter(s => s.change_pct < -9).length || 0}
              prefix={<FallOutlined />}
              suffix="只"
              valueStyle={{ color: '#3f8600' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="更新时间"
              value={refreshTime}
              valueStyle={{ fontSize: 16 }}
            />
          </Card>
        </Col>
      </Row>

      <Card title="集合竞价分析" extra={<a onClick={fetchAuctionData}>刷新</a>}>
        <Tabs defaultActiveKey="1">
          <TabPane tab="涨幅榜" key="1">
            <Table
              columns={changeColumns}
              dataSource={auctionData?.change_ranking || []}
              loading={loading}
              rowKey="stock_code"
              pagination={{ pageSize: 20 }}
              size="small"
            />
          </TabPane>

          <TabPane tab="成交量榜" key="2">
            <Table
              columns={changeColumns}
              dataSource={auctionData?.volume_ranking || []}
              loading={loading}
              rowKey="stock_code"
              pagination={{ pageSize: 20 }}
              size="small"
            />
          </TabPane>

          <TabPane tab="异动股票" key="3">
            <Table
              columns={abnormalColumns}
              dataSource={auctionData?.abnormal_stocks || []}
              loading={loading}
              rowKey="stock_code"
              pagination={{ pageSize: 20 }}
              size="small"
            />
          </TabPane>
        </Tabs>
      </Card>
    </div>
  );
};

export default CallAuction;