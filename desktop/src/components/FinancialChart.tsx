/**
 * FinancialChart - 金融图表组件
 * 使用 lightweight-charts 实现高性能K线和指标图表
 */

import {
  AreaSeries,
  CandlestickSeries,
  createChart,
  HistogramSeries,
  IChartApi,
  ISeriesApi,
  LineSeries,
  LineStyle,
  UTCTimestamp
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";

export interface CandlestickData {
  time: string | number; // YYYY-MM-DD or timestamp
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface LineData {
  time: string | number;
  value: number;
}

export interface FinancialChartProps {
  type: "candlestick" | "line" | "area";
  data: CandlestickData[] | LineData[];
  height?: number;
  title?: string;
  indicators?: {
    name: string;
    data: LineData[];
    color: string;
  }[];
  volumeData?: LineData[];
  showLegend?: boolean;
  showGrid?: boolean;
}

/**
 * 金融图表组件 - K线、折线、面积图
 *
 * @example
 * <FinancialChart
 *   type="candlestick"
 *   data={klineData}
 *   height={400}
 *   title="600519 日K线"
 *   indicators={[
 *     { name: 'MA5', data: ma5Data, color: '#2962FF' },
 *     { name: 'MA20', data: ma20Data, color: '#FF6D00' }
 *   ]}
 *   volumeData={volumeData}
 *   showLegend
 * />
 */
export function FinancialChart({
  type,
  data,
  height = 400,
  title,
  indicators,
  volumeData,
  showLegend = true,
  showGrid = true
}: FinancialChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const mainSeriesRef = useRef<ISeriesApi<any> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current || data.length === 0) return;

    try {
      // 创建图表
      const chart = createChart(chartContainerRef.current, {
        width: chartContainerRef.current.clientWidth,
        height: height,
        layout: {
          background: { color: "#ffffff" },
          textColor: "#18202c"
        },
        grid: {
          vertLines: { visible: showGrid, color: "#e0e3e7" },
          horzLines: { visible: showGrid, color: "#e0e3e7" }
        },
        crosshair: {
          mode: 1, // Normal
          vertLine: {
            width: 1,
            color: "#758696",
            style: LineStyle.Dashed
          },
          horzLine: {
            width: 1,
            color: "#758696",
            style: LineStyle.Dashed
          }
        },
        timeScale: {
          borderColor: "#d7dde8",
          timeVisible: true,
          secondsVisible: false
        },
        rightPriceScale: {
          borderColor: "#d7dde8"
        }
      });

      chartRef.current = chart;

      // 添加主系列
      let mainSeries: ISeriesApi<any>;

      if (type === "candlestick") {
        mainSeries = chart.addSeries(CandlestickSeries, {
          upColor: "#ef5350",
          downColor: "#26a69a",
          borderUpColor: "#ef5350",
          borderDownColor: "#26a69a",
          wickUpColor: "#ef5350",
          wickDownColor: "#26a69a"
        });

        // 转换时间格式
        const candleData = (data as CandlestickData[]).map((d) => ({
          time: (typeof d.time === "string" ? new Date(d.time).getTime() / 1000 : d.time) as UTCTimestamp,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close
        }));

        mainSeries.setData(candleData);
      } else if (type === "line") {
        mainSeries = chart.addSeries(LineSeries, {
          color: "#2962FF",
          lineWidth: 2
        });

        const lineData = (data as LineData[]).map((d) => ({
          time: (typeof d.time === "string" ? new Date(d.time).getTime() / 1000 : d.time) as UTCTimestamp,
          value: d.value
        }));

        mainSeries.setData(lineData);
      } else {
        // area
        mainSeries = chart.addSeries(AreaSeries, {
          topColor: "rgba(41, 98, 255, 0.4)",
          bottomColor: "rgba(41, 98, 255, 0.0)",
          lineColor: "#2962FF",
          lineWidth: 2
        });

        const areaData = (data as LineData[]).map((d) => ({
          time: (typeof d.time === "string" ? new Date(d.time).getTime() / 1000 : d.time) as UTCTimestamp,
          value: d.value
        }));

        mainSeries.setData(areaData);
      }

      mainSeriesRef.current = mainSeries;

        // 添加指标线
      if (indicators && indicators.length > 0) {
        indicators.forEach((indicator) => {
          const lineSeries = chart.addSeries(LineSeries, {
            color: indicator.color,
            lineWidth: 1,
            title: indicator.name
          });

          const indicatorData = indicator.data.map((d) => ({
            time: (typeof d.time === "string" ? new Date(d.time).getTime() / 1000 : d.time) as UTCTimestamp,
            value: d.value
          }));

          lineSeries.setData(indicatorData);
        });
      }

      // 添加成交量（副图）
      if (volumeData && volumeData.length > 0) {
        const volumeSeries = chart.addSeries(HistogramSeries, {
          color: "#26a69a",
          priceFormat: {
            type: "volume"
          },
          priceScaleId: "volume"
        });

        const volData = volumeData.map((d) => ({
          time: (typeof d.time === "string" ? new Date(d.time).getTime() / 1000 : d.time) as UTCTimestamp,
          value: d.value,
          color: d.value > 0 ? "#26a69a80" : "#ef535080"
        }));

        volumeSeries.setData(volData);

        chart.priceScale("volume").applyOptions({
          scaleMargins: {
            top: 0.8,
            bottom: 0
          }
        });
      }

      // 自适应时间范围
      chart.timeScale().fitContent();

      // 响应式调整
      const handleResize = () => {
        if (chartContainerRef.current && chartRef.current) {
          chartRef.current.applyOptions({
            width: chartContainerRef.current.clientWidth
          });
        }
      };

      window.addEventListener("resize", handleResize);

      return () => {
        window.removeEventListener("resize", handleResize);
        chart.remove();
        chartRef.current = null;
        mainSeriesRef.current = null;
      };
    } catch (err) {
      console.error("Chart initialization error:", err);
      setError(err instanceof Error ? err.message : "图表初始化失败");
    }
  }, [type, data, height, indicators, volumeData, showGrid]);

  if (error) {
    return (
      <div className="financial-chart-error" style={{ height }}>
        <AlertTriangle size={32} />
        <p>图表加载失败</p>
        <small>{error}</small>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="financial-chart-empty" style={{ height }}>
        <p>暂无图表数据</p>
      </div>
    );
  }

  return (
    <div className="financial-chart">
      {title && showLegend && (
        <div className="financial-chart-header">
          <h3>{title}</h3>
          {indicators && indicators.length > 0 && (
            <div className="financial-chart-legend">
              {indicators.map((ind) => (
                <span key={ind.name} className="legend-item">
                  <span className="legend-color" style={{ backgroundColor: ind.color }} />
                  {ind.name}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
      <div ref={chartContainerRef} className="financial-chart-container" />
    </div>
  );
}

/**
 * 简化的市场温度热力图
 */
export interface HeatmapData {
  industry: string;
  temperature: number; // 0-100
  stocks: number;
  avgChange: number;
}

export function MarketHeatmap({ data }: { data: HeatmapData[] }) {
  if (data.length === 0) {
    return (
      <div className="market-heatmap-empty">
        <p>暂无行业温度数据</p>
      </div>
    );
  }

  const getTemperatureColor = (temp: number) => {
    if (temp >= 80) return "#ef5350"; // 极热 - 红色
    if (temp >= 60) return "#ff9800"; // 偏热 - 橙色
    if (temp >= 40) return "#ffeb3b"; // 中性 - 黄色
    if (temp >= 20) return "#2196f3"; // 偏冷 - 蓝色
    return "#9c27b0"; // 极冷 - 紫色
  };

  return (
    <div className="market-heatmap">
      {data.map((item) => (
        <div
          key={item.industry}
          className="heatmap-cell"
          style={{
            backgroundColor: getTemperatureColor(item.temperature),
            flex: `${item.stocks} 1 auto`
          }}
          title={`${item.industry}: 温度${item.temperature}, ${item.stocks}只, 平均${item.avgChange > 0 ? "+" : ""}${item.avgChange.toFixed(2)}%`}
        >
          <div className="heatmap-cell-content">
            <strong>{item.industry}</strong>
            <span className="heatmap-temp">{item.temperature.toFixed(0)}</span>
            <span className="heatmap-change">{item.avgChange > 0 ? "+" : ""}{item.avgChange.toFixed(2)}%</span>
          </div>
        </div>
      ))}
    </div>
  );
}
