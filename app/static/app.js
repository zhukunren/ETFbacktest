(() => {
  const state = {
    holdings: [
      { code: "510300", name: "沪深300ETF", weight: 60 },
      { code: "518880", name: "黄金ETF", weight: 40 },
    ],
    strategy: "rebalance",
    chart: null,
    fundNavChart: null,
    searchTimer: null,
    searchRequestId: 0,
  };

  const $ = (selector) => document.querySelector(selector);
  const dom = {
    sourceState: $("#sourceState"),
    catalogCount: $("#catalogCount"),
    refreshCatalog: $("#refreshCatalog"),
    fundSearch: $("#fundSearch"),
    clearSearch: $("#clearSearch"),
    searchResults: $("#searchResults"),
    selectedFunds: $("#selectedFunds"),
    weightTotal: $("#weightTotal"),
    equalizeWeights: $("#equalizeWeights"),
    rebalanceTab: $("#rebalanceTab"),
    dcaTab: $("#dcaTab"),
    rebalanceSettings: $("#rebalanceSettings"),
    dcaSettings: $("#dcaSettings"),
    startDate: $("#startDate"),
    endDate: $("#endDate"),
    initialCapital: $("#initialCapital"),
    feeRate: $("#feeRate"),
    dcaFrequency: $("#dcaFrequency"),
    dcaMode: $("#dcaMode"),
    dcaValue: $("#dcaValue"),
    dcaValueLabel: $("#dcaValueLabel"),
    runBacktest: $("#runBacktest"),
    emptyState: $("#emptyState"),
    resultContent: $("#resultContent"),
    resultTitle: $("#resultTitle"),
    resultMeta: $("#resultMeta"),
    navChart: $("#navChart"),
    fundNavChart: $("#fundNavChart"),
    fundNavCaption: $("#fundNavCaption"),
    allocationBody: $("#allocationBody"),
    executionLines: $("#executionLines"),
    executionSummary: $("#executionSummary"),
    totalFees: $("#totalFees"),
    tradesBody: $("#tradesBody"),
    tradesCaption: $("#tradesCaption"),
    toast: $("#toast"),
  };

  const money = new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    currencyDisplay: "narrowSymbol",
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
  const number = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });
  const fundNavColors = ["#087c70", "#b77616", "#2d8f68", "#c2463c", "#176f9b", "#7a5c9e"];
  const percentage = (value, digits = 2) => `${(Number(value || 0) * 100).toFixed(digits)}%`;
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  }[character]));

  function initializeIcons() {
    if (window.lucide) window.lucide.createIcons({ attrs: { width: 16, height: 16 } });
  }

  function isoDate(date) {
    const offset = date.getTimezoneOffset();
    return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 10);
  }

  function setupDates() {
    const today = new Date();
    const start = new Date(today);
    start.setFullYear(start.getFullYear() - 3);
    dom.startDate.value = isoDate(start);
    dom.endDate.value = isoDate(today);
  }

  function setSourceStatus(text, type = "ready") {
    dom.sourceState.className = `source-state is-${type}`;
    dom.sourceState.innerHTML = `<span class="status-dot"></span>${escapeHtml(text)}`;
  }

  function showToast(message, isError = false) {
    dom.toast.textContent = message;
    dom.toast.className = `toast is-visible${isError ? " is-error" : ""}`;
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => {
      dom.toast.className = "toast";
    }, 3600);
  }

  async function requestJson(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "请求失败，请稍后重试");
    return data;
  }

  async function loadCatalogStatus() {
    try {
      const data = await requestJson("/api/catalog/status");
      dom.catalogCount.textContent = `${number.format(data.count || 0)} 只`;
      if (data.warning) {
        setSourceStatus("使用本地 ETF 目录", "warning");
      } else if (String(data.source).startsWith("akshare")) {
        setSourceStatus("目录已由 AkShare 更新", "ready");
      } else {
        setSourceStatus("使用本地 ETF 目录", "ready");
      }
    } catch (error) {
      setSourceStatus("目录暂不可用", "error");
    }
  }

  async function refreshCatalog() {
    dom.refreshCatalog.disabled = true;
    dom.refreshCatalog.classList.add("is-spinning");
    setSourceStatus("正在从 AkShare 更新目录");
    try {
      const data = await requestJson("/api/catalog/refresh", { method: "POST" });
      dom.catalogCount.textContent = `${number.format(data.count || 0)} 只`;
      setSourceStatus("目录已由 AkShare 更新", "ready");
      showToast(`已更新 ${number.format(data.count || 0)} 只 ETF`);
    } catch (error) {
      setSourceStatus("目录刷新失败，保留本地缓存", "warning");
      showToast(error.message, true);
    } finally {
      dom.refreshCatalog.disabled = false;
      dom.refreshCatalog.classList.remove("is-spinning");
    }
  }

  function totalWeight() {
    return state.holdings.reduce((sum, holding) => sum + (Number(holding.weight) || 0), 0);
  }

  function renderSelectedFunds() {
    const total = totalWeight();
    dom.selectedFunds.innerHTML = state.holdings.map((holding) => `
      <div class="selected-row" data-code="${escapeHtml(holding.code)}">
        <div class="fund-name">
          <strong>${escapeHtml(holding.name)}</strong>
          <code>${escapeHtml(holding.code)}</code>
        </div>
        <label class="weight-input-wrap">
          <span class="sr-only">${escapeHtml(holding.name)} 的权重</span>
          <input class="weight-input" type="number" min="0.01" max="100" step="0.01" value="${Number(holding.weight).toFixed(2)}" data-weight-code="${escapeHtml(holding.code)}" inputmode="decimal" />
          <span>%</span>
        </label>
        <button class="icon-button remove-holding" type="button" aria-label="移除 ${escapeHtml(holding.name)}" data-remove-code="${escapeHtml(holding.code)}" data-tooltip="移除基金"><i data-lucide="trash-2" aria-hidden="true"></i></button>
      </div>
    `).join("");
    dom.weightTotal.textContent = `${total.toFixed(2)}%`;
    dom.weightTotal.classList.toggle("is-invalid", Math.abs(total - 100) > 0.01);
    initializeIcons();
  }

  function hideSearchResults() {
    state.searchRequestId += 1;
    dom.searchResults.hidden = true;
    dom.searchResults.innerHTML = "";
  }

  function renderSearchResults(items, query) {
    if (!items.length) {
      dom.searchResults.innerHTML = `<div class="search-empty">未找到“${escapeHtml(query)}”相关 ETF</div>`;
    } else {
      dom.searchResults.innerHTML = items.map((item) => `
        <button class="search-item" type="button" role="option" data-add-code="${escapeHtml(item.code)}" data-add-name="${escapeHtml(item.name)}">
          <strong>${escapeHtml(item.name)}</strong><code>${escapeHtml(item.code)}</code>
        </button>
      `).join("");
    }
    dom.searchResults.hidden = false;
  }

  async function searchFunds() {
    const query = dom.fundSearch.value.trim();
    const requestId = ++state.searchRequestId;
    dom.clearSearch.hidden = !query;
    try {
      const data = await requestJson(`/api/etfs/search?q=${encodeURIComponent(query)}`);
      if (requestId !== state.searchRequestId) return;
      renderSearchResults(data.items || [], query || "热门基金");
    } catch (error) {
      if (requestId !== state.searchRequestId) return;
      renderSearchResults([], query);
    }
  }

  function addHolding(code, name) {
    if (state.holdings.some((holding) => holding.code === code)) {
      showToast("该 ETF 已在组合中");
      return;
    }
    state.holdings.push({ code, name, weight: 0 });
    equalizeWeights();
    dom.fundSearch.value = "";
    dom.clearSearch.hidden = true;
    hideSearchResults();
  }

  function equalizeWeights() {
    const weight = 100 / state.holdings.length;
    state.holdings = state.holdings.map((holding) => ({ ...holding, weight }));
    renderSelectedFunds();
  }

  function updateStrategy(strategy) {
    state.strategy = strategy;
    const isRebalance = strategy === "rebalance";
    dom.rebalanceTab.classList.toggle("is-active", isRebalance);
    dom.dcaTab.classList.toggle("is-active", !isRebalance);
    dom.rebalanceTab.setAttribute("aria-selected", String(isRebalance));
    dom.dcaTab.setAttribute("aria-selected", String(!isRebalance));
    dom.rebalanceSettings.hidden = !isRebalance;
    dom.dcaSettings.hidden = isRebalance;
  }

  function updateDcaValueLabel() {
    const isShares = dom.dcaMode.value === "shares";
    dom.dcaValueLabel.textContent = isShares ? "每只基金每期份额" : "每期金额（元）";
    dom.dcaValue.step = isShares ? "1" : "100";
    dom.dcaValue.value = isShares ? "100" : "2000";
  }

  function readRadio(name) {
    return document.querySelector(`input[name="${name}"]:checked`)?.value;
  }

  function payload() {
    return {
      holdings: state.holdings.map((holding) => ({
        code: holding.code,
        name: holding.name,
        weight: Number(holding.weight),
      })),
      start_date: dom.startDate.value,
      end_date: dom.endDate.value,
      initial_capital: Number(dom.initialCapital.value || 0),
      strategy: state.strategy,
      rebalance_frequency: state.strategy === "rebalance" ? readRadio("rebalanceFreq") : readRadio("dcaRebalanceFreq"),
      dca_frequency: dom.dcaFrequency.value,
      dca_mode: dom.dcaMode.value,
      dca_value: Number(dom.dcaValue.value || 0),
      fee_rate: Number(dom.feeRate.value || 0) / 100,
    };
  }

  function validatePayload(data) {
    if (!data.holdings.length) return "请至少添加一只 ETF";
    if (data.holdings.some((holding) => !holding.weight || holding.weight <= 0)) return "每只 ETF 都需要大于 0 的目标权重";
    if (Math.abs(totalWeight() - 100) > 0.01) return "目标权重合计必须为 100%";
    if (!data.start_date || !data.end_date || data.start_date >= data.end_date) return "请设置有效的回测区间";
    if (data.initial_capital < 0 || data.fee_rate < 0) return "资金和费率不能为负数";
    if (data.strategy === "dca" && data.dca_value <= 0) return "定投金额或份额必须大于 0";
    return null;
  }

  function valueClass(value) {
    return Number(value) > 0 ? "positive" : Number(value) < 0 ? "negative" : "";
  }

  function setMetric(id, text, tone) {
    const element = $(id);
    element.textContent = text;
    element.className = tone ? tone : "";
  }

  function renderMetrics(metrics) {
    setMetric("#metricFinalValue", money.format(metrics.final_value));
    $("#metricProfit").textContent = `收益 ${money.format(metrics.profit)}`;
    setMetric("#metricCapitalReturn", percentage(metrics.capital_return), valueClass(metrics.capital_return));
    $("#metricInvested").textContent = `累计投入 ${money.format(metrics.invested_capital)}`;
    setMetric("#metricAnnualized", percentage(metrics.annualized_return), valueClass(metrics.annualized_return));
    setMetric("#metricDrawdown", percentage(metrics.max_drawdown), "negative");
    $("#metricVolatility").textContent = `年化波动 ${percentage(metrics.annualized_volatility)}`;
  }

  function renderChart(series) {
    if (!window.echarts) return;
    if (state.chart) state.chart.dispose();
    state.chart = window.echarts.init(dom.navChart, null, { renderer: "canvas" });
    state.chart.setOption({
      animationDuration: 280,
      animationEasing: "cubicOut",
      grid: { left: 60, right: 22, top: 15, bottom: 48 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(25, 39, 34, 0.96)",
        borderWidth: 0,
        textStyle: { color: "#fff", fontSize: 12 },
        valueFormatter: (value) => money.format(value),
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: series.dates,
        axisLine: { lineStyle: { color: "#bdcbc4" } },
        axisTick: { show: false },
        axisLabel: { color: "#68746f", fontSize: 11, hideOverlap: true, margin: 13 },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: "#e1e8e4" } },
        axisLabel: { color: "#68746f", fontSize: 11, formatter: (value) => number.format(value) },
      },
      dataZoom: [{ type: "inside", start: 0, end: 100 }],
      series: [
        {
          name: "组合资产",
          type: "line",
          data: series.nav,
          showSymbol: false,
          smooth: false,
          lineStyle: { width: 2, color: "#087c70" },
          itemStyle: { color: "#087c70" },
        },
        {
          name: "累计投入",
          type: "line",
          data: series.invested,
          showSymbol: false,
          smooth: false,
          lineStyle: { width: 2, color: "#b77616", type: "dashed" },
          itemStyle: { color: "#b77616" },
        },
      ],
    });
  }

  function renderFundNavChart(fundNav, dates) {
    if (!window.echarts || !fundNav?.items?.length) return;
    if (state.fundNavChart) state.fundNavChart.dispose();
    state.fundNavChart = window.echarts.init(dom.fundNavChart, null, { renderer: "canvas" });
    dom.fundNavCaption.textContent = `相对净值，${fundNav.base_date} = 1.0000`;
    const labels = fundNav.items.map((item) => `${item.name} (${item.code})`);
    state.fundNavChart.setOption({
      color: fundNavColors,
      animationDuration: 280,
      animationEasing: "cubicOut",
      grid: { left: 54, right: 22, top: 52, bottom: 48 },
      legend: {
        type: "scroll",
        top: 4,
        left: 0,
        right: 0,
        data: labels,
        textStyle: { color: "#68746f", fontSize: 12 },
      },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(25, 39, 34, 0.96)",
        borderWidth: 0,
        textStyle: { color: "#fff", fontSize: 12 },
        valueFormatter: (value) => Number(value).toFixed(4),
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: dates,
        axisLine: { lineStyle: { color: "#bdcbc4" } },
        axisTick: { show: false },
        axisLabel: { color: "#68746f", fontSize: 11, hideOverlap: true, margin: 13 },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: "#e1e8e4" } },
        axisLabel: { color: "#68746f", fontSize: 11, formatter: (value) => Number(value).toFixed(2) },
      },
      dataZoom: [{ type: "inside", start: 0, end: 100 }],
      series: fundNav.items.map((item, index) => ({
        name: labels[index],
        type: "line",
        data: item.values,
        showSymbol: false,
        smooth: false,
        lineStyle: { width: 2 },
      })),
    });
  }

  function renderAllocation(allocation) {
    dom.allocationBody.innerHTML = allocation.map((row) => `
      <tr>
        <td class="fund-cell"><strong>${escapeHtml(row.name)}</strong><span>${escapeHtml(row.code)}</span></td>
        <td class="numeric">${percentage(row.target_weight)}</td>
        <td class="numeric">${percentage(row.actual_weight)}</td>
        <td class="numeric">${row.relative_nav === null ? "--" : Number(row.relative_nav).toFixed(4)}</td>
        <td class="numeric">${row.period_return === null ? "--" : percentage(row.period_return)}</td>
        <td class="numeric">${money.format(row.value)}</td>
      </tr>
    `).join("");
  }

  function renderExecution(metrics, meta) {
    dom.executionSummary.textContent = `${meta.price_basis} · ${metrics.trading_days} 个交易日`;
    dom.totalFees.textContent = `手续费 ${money.format(metrics.total_fees)}`;
    const rows = [
      ["时间加权收益", percentage(metrics.time_weighted_return)],
      ["年化波动率", percentage(metrics.annualized_volatility)],
      ["夏普比率", metrics.sharpe === null ? "--" : Number(metrics.sharpe).toFixed(2)],
      ["交易笔数", `${number.format(metrics.trade_count)} 笔`],
    ];
    dom.executionLines.innerHTML = rows.map(([label, value]) => `<div class="execution-line"><span>${label}</span><strong>${value}</strong></div>`).join("");
  }

  function renderTrades(trades) {
    dom.tradesCaption.textContent = `共 ${number.format(trades.length)} 笔，按日期倒序`;
    dom.tradesBody.innerHTML = trades.map((trade) => `
      <tr>
        <td>${escapeHtml(trade.date)}</td>
        <td>${escapeHtml(trade.code)}</td>
        <td class="side-${trade.side === "buy" ? "buy" : "sell"}">${trade.side === "buy" ? "买入" : "卖出"}</td>
        <td class="numeric">${number.format(trade.shares)}</td>
        <td class="numeric">${number.format(trade.price)}</td>
        <td class="numeric">${money.format(trade.gross_value)}</td>
        <td class="numeric">${money.format(trade.fee)}</td>
        <td>${escapeHtml(trade.reason)}</td>
      </tr>
    `).join("");
  }

  function renderResults(result) {
    dom.emptyState.hidden = true;
    dom.resultContent.hidden = false;
    dom.resultTitle.textContent = state.strategy === "rebalance" ? "定期再平衡结果" : "定投计划结果";
    dom.resultMeta.textContent = `${result.meta.start_date} 至 ${result.meta.end_date}`;
    renderMetrics(result.metrics);
    renderChart(result.series);
    renderFundNavChart(result.series.fund_nav, result.series.dates);
    renderAllocation(result.allocation);
    renderExecution(result.metrics, result.meta);
    renderTrades(result.trades);
  }

  async function runBacktest() {
    const data = payload();
    const problem = validatePayload(data);
    if (problem) {
      showToast(problem, true);
      return;
    }
    dom.runBacktest.disabled = true;
    dom.runBacktest.querySelector("span").textContent = "正在获取行情";
    try {
      const result = await requestJson("/api/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      renderResults(result);
      showToast("回测完成");
    } catch (error) {
      showToast(error.message, true);
    } finally {
      dom.runBacktest.disabled = false;
      dom.runBacktest.querySelector("span").textContent = "运行回测";
    }
  }

  function bindEvents() {
    dom.refreshCatalog.addEventListener("click", refreshCatalog);
    dom.fundSearch.addEventListener("input", () => {
      window.clearTimeout(state.searchTimer);
      state.searchTimer = window.setTimeout(searchFunds, 160);
    });
    dom.fundSearch.addEventListener("focus", () => {
      if (dom.searchResults.hidden) searchFunds();
    });
    dom.clearSearch.addEventListener("click", () => {
      dom.fundSearch.value = "";
      dom.clearSearch.hidden = true;
      dom.fundSearch.focus();
      searchFunds();
    });
    dom.searchResults.addEventListener("click", (event) => {
      const item = event.target.closest("[data-add-code]");
      if (item) addHolding(item.dataset.addCode, item.dataset.addName);
    });
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".search-control")) hideSearchResults();
    });
    dom.selectedFunds.addEventListener("input", (event) => {
      const input = event.target.closest("[data-weight-code]");
      if (!input) return;
      const holding = state.holdings.find((item) => item.code === input.dataset.weightCode);
      if (holding) holding.weight = Number(input.value);
      const total = totalWeight();
      dom.weightTotal.textContent = `${total.toFixed(2)}%`;
      dom.weightTotal.classList.toggle("is-invalid", Math.abs(total - 100) > 0.01);
    });
    dom.selectedFunds.addEventListener("click", (event) => {
      const button = event.target.closest("[data-remove-code]");
      if (!button) return;
      state.holdings = state.holdings.filter((holding) => holding.code !== button.dataset.removeCode);
      if (state.holdings.length) {
        equalizeWeights();
      } else {
        renderSelectedFunds();
      }
    });
    dom.equalizeWeights.addEventListener("click", () => {
      if (!state.holdings.length) return;
      equalizeWeights();
    });
    dom.rebalanceTab.addEventListener("click", () => updateStrategy("rebalance"));
    dom.dcaTab.addEventListener("click", () => updateStrategy("dca"));
    dom.dcaMode.addEventListener("change", updateDcaValueLabel);
    dom.runBacktest.addEventListener("click", runBacktest);
    window.addEventListener("resize", () => {
      state.chart?.resize();
      state.fundNavChart?.resize();
    });
  }

  function init() {
    setupDates();
    renderSelectedFunds();
    bindEvents();
    initializeIcons();
    loadCatalogStatus();
  }

  init();
})();
