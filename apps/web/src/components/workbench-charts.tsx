"use client";

// Bu bilesen, workbench charts arayuz parcasini kurar.

import dynamic from "next/dynamic";

const ReactECharts = dynamic(async () => (await import("echarts-for-react")).default, {
  ssr: false,
});

type TrendPoint = {
  label: string;
  value: number;
};

function toneColor(tone?: "good" | "attention" | "critical" | "neutral"): string {
  if (tone === "good") return "#1f7a4a";
  if (tone === "critical") return "#bf655a";
  if (tone === "attention") return "#c79a37";
  return "#5f7866";
}

function toneArea(tone?: "good" | "attention" | "critical" | "neutral"): string {
  if (tone === "good") return "rgba(31, 122, 74, 0.18)";
  if (tone === "critical") return "rgba(191, 101, 90, 0.16)";
  if (tone === "attention") return "rgba(199, 154, 55, 0.18)";
  return "rgba(95, 120, 102, 0.15)";
}

function chartText(color = "#7c756b") {
  return { color, fontFamily: "Inter", fontSize: 11 };
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
  const area = toneArea(tone);
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
              { offset: 0, color: area },
              { offset: 1, color: "rgba(255,255,255,0.02)" },
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
  const safeValue = Math.max(0, Math.min(100, value));
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
          { value: safeValue, itemStyle: { color } },
          { value: Math.max(0, 100 - safeValue), itemStyle: { color: "rgba(23,22,19,0.08)" } },
        ],
      },
    ],
    graphic: [
      {
        type: "text",
        left: "center",
        top: "38%",
        style: {
          text: `${Math.round(safeValue)}%`,
          fontSize: 30,
          fontWeight: 600,
          fill: "#171613",
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
          fill: "#898377",
          fontFamily: "Inter",
        },
      },
    ],
  };

  return <ReactECharts option={option} notMerge lazyUpdate style={{ height, width: "100%" }} />;
}

export function CapsuleBarChart({
  points,
  highlightIndex,
  height = 180,
}: {
  points: TrendPoint[];
  highlightIndex?: number;
  height?: number;
}) {
  const option = {
    animationDuration: 420,
    grid: { top: 10, right: 8, bottom: 24, left: 8 },
    xAxis: {
      type: "category",
      data: points.map((point) => point.label),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: chartText(),
    },
    yAxis: { type: "value", show: false },
    series: [
      {
        type: "bar",
        showBackground: true,
        backgroundStyle: {
          color: "rgba(23,22,19,0.06)",
          borderRadius: [999, 999, 999, 999],
        },
        barWidth: 22,
        data: points.map((point, index) => ({
          value: point.value,
          itemStyle: {
            color:
              typeof highlightIndex === "number" && index === highlightIndex
                ? "#1f7a4a"
                : index % 2 === 0
                  ? "rgba(31,122,74,0.72)"
                  : "rgba(137,131,119,0.26)",
            borderRadius: [999, 999, 999, 999],
          },
        })),
      },
    ],
  };

  return <ReactECharts option={option} notMerge lazyUpdate style={{ height, width: "100%" }} />;
}

export function FocusLineChart({
  series,
  height = 220,
}: {
  series: Array<{ label: string; points: TrendPoint[]; color?: string }>;
  height?: number;
}) {
  const labels = series[0]?.points.map((point) => point.label) ?? [];
  const palette = ["#1f7a4a", "#22211e", "#d2a742", "#8cad95"];
  const option = {
    animationDuration: 440,
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(255,255,255,0.96)",
      borderColor: "rgba(23,22,19,0.08)",
      textStyle: { color: "#171613", fontFamily: "Inter" },
    },
    legend: {
      top: 0,
      right: 0,
      icon: "circle",
      itemWidth: 8,
      itemHeight: 8,
      textStyle: chartText(),
    },
    grid: { top: 34, right: 8, bottom: 18, left: 8 },
    xAxis: {
      type: "category",
      data: labels,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: chartText(),
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
      axisLabel: { show: false },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: "rgba(23,22,19,0.05)" } },
    },
    series: series.map((entry, index) => ({
      name: entry.label,
      type: "line",
      smooth: true,
      symbol: "circle",
      symbolSize: 7,
      data: entry.points.map((point) => point.value),
      lineStyle: {
        width: 3,
        color: entry.color ?? palette[index % palette.length],
      },
      itemStyle: {
        color: entry.color ?? palette[index % palette.length],
        borderColor: "#ffffff",
        borderWidth: 2,
      },
      areaStyle:
        index === 0
          ? {
              color: {
                type: "linear",
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  { offset: 0, color: "rgba(31,122,74,0.14)" },
                  { offset: 1, color: "rgba(31,122,74,0.02)" },
                ],
              },
            }
          : undefined,
    })),
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
      axisLabel: chartText(),
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
                ? "#1f7a4a"
                : "rgba(23,22,19,0.72)",
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
      axisLabel: chartText(),
    },
    yAxis: { type: "value", show: false },
    series: [
      {
        type: "bar",
        stack: "total",
        data: data.map((item) => item.values[0] ?? 0),
        itemStyle: { color: "#1f7a4a", borderRadius: [999, 999, 0, 0] },
        barWidth: 14,
      },
      {
        type: "bar",
        stack: "total",
        data: data.map((item) => item.values[1] ?? 0),
        itemStyle: { color: "#d2a742" },
      },
      {
        type: "bar",
        stack: "total",
        data: data.map((item) => item.values[2] ?? 0),
        itemStyle: { color: "rgba(23,22,19,0.14)", borderRadius: [0, 0, 999, 999] },
      },
    ],
  };

  return <ReactECharts option={option} notMerge lazyUpdate style={{ height, width: "100%" }} />;
}
