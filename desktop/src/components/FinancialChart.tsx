import { AlertTriangle } from "lucide-react";
import {
  AreaSeries,
  CandlestickSeries,
  createChart,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  LineSeries,
  LineStyle,
  type UTCTimestamp
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

export interface CandlestickData {
  time: string | number;
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

function toUtcTimestamp(value: string | number) {
  return (typeof value === "string" ? new Date(value).getTime() / 1000 : value) as UTCTimestamp;
}

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
      const chart = createChart(chartContainerRef.current, {
        width: chartContainerRef.current.clientWidth,
        height,
        layout: {
          background: { color: "#ffffff" },
          textColor: "#18202c"
        },
        grid: {
          vertLines: { visible: showGrid, color: "#e0e3e7" },
          horzLines: { visible: showGrid, color: "#e0e3e7" }
        },
        crosshair: {
          mode: 1,
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

        mainSeries.setData(
          (data as CandlestickData[]).map((item) => ({
            time: toUtcTimestamp(item.time),
            open: item.open,
            high: item.high,
            low: item.low,
            close: item.close
          }))
        );
      } else if (type === "line") {
        mainSeries = chart.addSeries(LineSeries, {
          color: "#2962FF",
          lineWidth: 2
        });

        mainSeries.setData(
          (data as LineData[]).map((item) => ({
            time: toUtcTimestamp(item.time),
            value: item.value
          }))
        );
      } else {
        mainSeries = chart.addSeries(AreaSeries, {
          topColor: "rgba(41, 98, 255, 0.4)",
          bottomColor: "rgba(41, 98, 255, 0)",
          lineColor: "#2962FF",
          lineWidth: 2
        });

        mainSeries.setData(
          (data as LineData[]).map((item) => ({
            time: toUtcTimestamp(item.time),
            value: item.value
          }))
        );
      }

      mainSeriesRef.current = mainSeries;

      if (indicators?.length) {
        indicators.forEach((indicator) => {
          const lineSeries = chart.addSeries(LineSeries, {
            color: indicator.color,
            lineWidth: 1,
            title: indicator.name
          });

          lineSeries.setData(
            indicator.data.map((item) => ({
              time: toUtcTimestamp(item.time),
              value: item.value
            }))
          );
        });
      }

      if (volumeData?.length) {
        const volumeSeries = chart.addSeries(HistogramSeries, {
          color: "#26a69a",
          priceFormat: {
            type: "volume"
          },
          priceScaleId: "volume"
        });

        volumeSeries.setData(
          volumeData.map((item) => ({
            time: toUtcTimestamp(item.time),
            value: item.value,
            color: item.value > 0 ? "#26a69a80" : "#ef535080"
          }))
        );

        chart.priceScale("volume").applyOptions({
          scaleMargins: {
            top: 0.8,
            bottom: 0
          }
        });
      }

      chart.timeScale().fitContent();

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
  }, [data, height, indicators, showGrid, type, volumeData]);

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
      {title && showLegend ? (
        <div className="financial-chart-header">
          <h3>{title}</h3>
          {indicators?.length ? (
            <div className="financial-chart-legend">
              {indicators.map((indicator) => (
                <span key={indicator.name} className="legend-item">
                  <span className="legend-color" style={{ backgroundColor: indicator.color }} />
                  {indicator.name}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
      <div ref={chartContainerRef} className="financial-chart-container" />
    </div>
  );
}

export interface HeatmapData {
  industry: string;
  temperature: number;
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

  const getTemperatureColor = (temperature: number) => {
    if (temperature >= 80) return "#ef5350";
    if (temperature >= 60) return "#ff9800";
    if (temperature >= 40) return "#ffeb3b";
    if (temperature >= 20) return "#2196f3";
    return "#9c27b0";
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
          title={`${item.industry}: 温度 ${item.temperature}，${item.stocks} 只，平均涨跌 ${item.avgChange > 0 ? "+" : ""}${item.avgChange.toFixed(2)}%`}
        >
          <div className="heatmap-cell-content">
            <strong>{item.industry}</strong>
            <span className="heatmap-temp">{item.temperature.toFixed(0)}</span>
            <span className="heatmap-change">
              {item.avgChange > 0 ? "+" : ""}
              {item.avgChange.toFixed(2)}%
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
