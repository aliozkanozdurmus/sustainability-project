"use client";

import dynamic from "next/dynamic";

const ReactECharts = dynamic(async () => (await import("echarts-for-react")).default, {
  ssr: false,
});

type TrendPoint = {
  label: string;
  value: number;
};

function toneColor(tone?: "good" | "attention" | "critical" | "neutral"): string {
  if (tone === "good") return "var(--success)";
  if (tone === "critical") return "var(--destructive)";
  if (tone === "attention") return "var(--accent-strong)";
  return "var(--chart-2)";
}

export function SparklineArea({
  points,
  height = 108,
  tone = "attention",
}: {
  points: TrendPoint[];
  height?: number;
  tone?: "good" | "attention" | "critical" | "neutral";
}) {
  const color = toneColor(tone);
  const option = {
    animationDuration: 360,
    grid: { top: 12, right: 4, bottom: 6, left: 4 },
    xAxis: {
      type: "category",
      data: points.map((point) => point.label),
      show: false,
    },
    yAxis: { type: "value", show: false },
    series: [
      {
        type: "line",
        smooth: true,
        symbol: "none",
        data: points.map((point) => point.value),
        lineStyle: { color, width: 3 },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(228, 199, 100, 0.36)" },
              { offset: 1, color: "rgba(228, 199, 100, 0.02)" },
            ],
          },
        },
      },
    ],
  };

  return <ReactECharts option={option} notMerge lazyUpdate style={{ height, width: "100%" }} />;
}

export function RadialMetricChart({
  value,
  label,
  tone = "attention",
  height = 180,
}: {
  value: number;
  label: string;
  tone?: "good" | "attention" | "critical" | "neutral";
  height?: number;
}) {
  const color = toneColor(tone);
  const option = {
    animationDuration: 420,
    series: [
      {
        type: "pie",
        radius: ["68%", "82%"],
        center: ["50%", "50%"],
        silent: true,
        label: { show: false },
        data: [
          { value, itemStyle: { color } },
          { value: Math.max(0, 100 - value), itemStyle: { color: "rgba(37,35,31,0.08)" } },
        ],
      },
    ],
    graphic: [
      {
        type: "text",
        left: "center",
        top: "40%",
        style: {
          text: `${Math.round(value)}%`,
          fontSize: 28,
          fontWeight: 600,
          fill: "#25231f",
          fontFamily: "Inter",
        },
      },
      {
        type: "text",
        left: "center",
        top: "59%",
        style: {
          text: label,
          fontSize: 12,
          fill: "#7d7568",
          fontFamily: "Inter",
        },
      },
    ],
  };

  return <ReactECharts option={option} notMerge lazyUpdate style={{ height, width: "100%" }} />;
}

export function MiniBarChart({
  points,
  highlightIndex,
  height = 132,
}: {
  points: TrendPoint[];
  highlightIndex?: number;
  height?: number;
}) {
  const option = {
    animationDuration: 380,
    grid: { top: 8, right: 8, bottom: 20, left: 8 },
    xAxis: {
      type: "category",
      data: points.map((point) => point.label),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: "#7d7568", fontSize: 11 },
    },
    yAxis: { type: "value", show: false },
    series: [
      {
        type: "bar",
        data: points.map((point, index) => ({
          value: point.value,
          itemStyle: {
            color:
              typeof highlightIndex === "number" && highlightIndex === index
                ? "var(--accent)"
                : "rgba(37,35,31,0.7)",
            borderRadius: [999, 999, 999, 999],
          },
        })),
        barWidth: 8,
      },
    ],
  };

  return <ReactECharts option={option} notMerge lazyUpdate style={{ height, width: "100%" }} />;
}

export function StackedBarChart({
  data,
  height = 180,
}: {
  data: Array<{ label: string; values: number[] }>;
  height?: number;
}) {
  const option = {
    animationDuration: 420,
    grid: { top: 10, right: 10, bottom: 28, left: 6 },
    xAxis: {
      type: "category",
      data: data.map((item) => item.label),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: "#7d7568", fontSize: 11 },
    },
    yAxis: { type: "value", show: false },
    series: [
      { type: "bar", stack: "total", data: data.map((item) => item.values[0] ?? 0), itemStyle: { color: "var(--chart-2)", borderRadius: [999, 999, 0, 0] }, barWidth: 14 },
      { type: "bar", stack: "total", data: data.map((item) => item.values[1] ?? 0), itemStyle: { color: "var(--accent)" } },
      { type: "bar", stack: "total", data: data.map((item) => item.values[2] ?? 0), itemStyle: { color: "rgba(37,35,31,0.16)", borderRadius: [0, 0, 999, 999] } },
    ],
  };

  return <ReactECharts option={option} notMerge lazyUpdate style={{ height, width: "100%" }} />;
}
