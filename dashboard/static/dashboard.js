function parseChartData(id) {
  const node = document.getElementById(id);
  if (!node) {
    return [];
  }

  try {
    return JSON.parse(node.textContent || "[]");
  } catch {
    return [];
  }
}

function metricField() {
  const select = document.querySelector('select[name="metric"]');
  return select ? select.value : "cost";
}

function metricLabel(metric) {
  if (metric === "tokens") return "Tokens";
  if (metric === "sessions") return "Sessions";
  return "Cost";
}

function metricValue(row, metric) {
  if (metric === "tokens") return Number(row.tokens || 0);
  if (metric === "sessions") return Number(row.sessions || 0);
  return Number(row.cost || 0);
}

function formatMetric(value, metric) {
  if (metric === "sessions") return `${Math.round(value)}`;
  if (metric === "tokens") return Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value);
  return Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value);
}

function buildRankChartOption(rows, metric) {
  return {
    grid: { left: 120, right: 20, top: 20, bottom: 20 },
    xAxis: { type: "value", splitLine: { show: false } },
    yAxis: {
      type: "category",
      data: rows.map((row) => row.label),
      axisTick: { show: false },
      axisLine: { show: false },
    },
    series: [
      {
        type: "bar",
        data: rows.map((row) => metricValue(row, metric)),
        itemStyle: { color: "#1d666b", borderRadius: [0, 8, 8, 0] },
        label: {
          show: true,
          position: "right",
          formatter: (value) => formatMetric(value.value, metric),
        },
      },
    ],
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (items) => {
        const item = items[0];
        return `${item.name}<br>${metricLabel(metric)}: ${formatMetric(item.value, metric)}`;
      },
    },
  };
}

function buildTrendChartOption(rows, metric) {
  return {
    grid: { left: 48, right: 16, top: 20, bottom: 32 },
    xAxis: {
      type: "category",
      data: rows.map((row) => row.day),
      axisLabel: { hideOverlap: true },
    },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "rgba(82, 63, 39, 0.12)" } } },
    series: [
      {
        type: "line",
        smooth: true,
        areaStyle: { color: "rgba(29, 102, 107, 0.12)" },
        lineStyle: { color: "#1d666b", width: 3 },
        symbol: "none",
        data: rows.map((row) => metricValue(row, metric)),
      },
    ],
    tooltip: {
      trigger: "axis",
      formatter: (items) => {
        const item = items[0];
        return `${rows[item.dataIndex].day}<br>${metricLabel(metric)}: ${formatMetric(item.value, metric)}`;
      },
    },
  };
}

function initChart(node) {
  if (!window.echarts) {
    return;
  }

  const chartName = node.dataset.chart;
  const rows = parseChartData(`${chartName}-data`);
  if (!rows.length) {
    return;
  }

  const chart = echarts.init(node);
  const metric = metricField();
  const option = chartName.includes("trend")
    ? buildTrendChartOption(rows, metric)
    : buildRankChartOption(rows, metric);

  chart.setOption(option);
  window.addEventListener("resize", () => chart.resize());
}

function initWorkspaceRows() {
  document.querySelectorAll(".js-workspace-row").forEach((row) => {
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        window.location.href = row.href;
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".js-chart").forEach(initChart);
  initWorkspaceRows();
});
