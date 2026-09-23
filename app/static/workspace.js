/* Progressive workspace UI. No API calls and no changes to backtest payloads. */
(() => {
  "use strict";
  const $ = (selector) => document.querySelector(selector);
  const workspace = $("#workspace");
  const configuration = $("#configurationPanel");
  const toggle = $("#toggleConfiguration");
  const resultContent = $("#resultContent");
  const runButton = $("#runBacktest");
  const fundList = $("#selectedFunds");
  const links = Array.from(document.querySelectorAll(".main-nav a"));
  const colors = ["#0079c2", "#8c91a2", "#6ebb79", "#f24040", "#034888", "#faa245"];
  if (!workspace || !configuration || !toggle || !resultContent || !runButton || !fundList) return;

  // Keep branding legible when the logo asset is unavailable.
  const logo = $(".brand-logo img");
  const logoFallback = () => logo?.parentElement.classList.add("has-fallback");
  logo?.addEventListener("error", logoFallback);
  if (logo?.complete && !logo.naturalWidth) logoFallback();

  const date = $("#workspaceDate");
  const today = new Date();
  date.textContent = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }).format(today);
  date.dateTime = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;

  let resizeFrame = 0;
  function resizeCharts() {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(() => {
      [$("#navChart"), $("#fundNavChart")].forEach((element) => {
        if (element && element.clientWidth && element.clientHeight) {
          window.echarts?.getInstanceByDom(element)?.resize();
        }
      });
    });
  }
  function setFocused(focused) {
    workspace.classList.toggle("is-focused", focused);
    toggle.setAttribute("aria-expanded", String(!focused));
    toggle.querySelector("span").textContent = focused ? "展开参数" : "收起参数";
    resizeCharts();
  }
  toggle.addEventListener("click", () => setFocused(!workspace.classList.contains("is-focused")));
  const compact = window.matchMedia("(max-width: 980px)");
  compact.addEventListener("change", (event) => { if (event.matches) setFocused(false); });

  function activateLink(link) {
    links.forEach((item) => {
      item.classList.toggle("is-active", item === link);
      if (item === link) item.setAttribute("aria-current", "location");
      else item.removeAttribute("aria-current");
    });
  }
  function goToConfiguration(event) {
    event.preventDefault();
    setFocused(false);
    configuration.scrollIntoView({ block: "start" });
    $("#fundSearch").focus({ preventScroll: true });
    activateLink(links[0]);
  }
  links.forEach((link) => link.addEventListener("click", (event) => {
    if (link.getAttribute("aria-disabled") === "true") {
      event.preventDefault();
      setFocused(false);
      runButton.focus();
      return;
    }
    if (link.getAttribute("href") === "#configurationPanel") goToConfiguration(event);
    else activateLink(link);
  }));
  $(".empty-action")?.addEventListener("click", goToConfiguration);

  function updateWeights() {
    const inputs = Array.from(fundList.querySelectorAll("[data-weight-code]"));
    $("#selectedCount").textContent = String(inputs.length);
    const weights = inputs.map((input) => Math.max(0, Number(input.value) || 0));
    const total = weights.reduce((sum, value) => sum + value, 0);
    const scale = Math.max(100, total);
    const bars = document.createDocumentFragment();
    inputs.forEach((input, index) => {
      const bar = document.createElement("span");
      bar.style.width = `${weights[index] / scale * 100}%`;
      bar.style.backgroundColor = colors[index % colors.length];
      bars.appendChild(bar);
    });
    $("#weightTrack").replaceChildren(bars);
    const displayedTotal = Number.parseFloat($("#weightTotal").textContent);
    $("#weightHint").textContent = inputs.length && Math.abs(displayedTotal - 100) <= 0.01 ? "权重已就绪" : "请将总权重调整为 100%";
  }
  fundList.addEventListener("input", updateWeights);
  new MutationObserver(updateWeights).observe(fundList, { childList: true });
  updateWeights();

  function updateResultState() {
    const ready = !resultContent.hidden;
    document.querySelectorAll("[data-needs-result]").forEach((link) => {
      link.setAttribute("aria-disabled", String(!ready));
      link.title = ready ? "" : "运行回测后可用";
    });
    if (ready && !window.echarts) {
      [$("#navChart"), $("#fundNavChart")].forEach((element) => {
        if (element.querySelector(".chart-unavailable")) return;
        const notice = document.createElement("p");
        notice.className = "chart-unavailable";
        notice.textContent = "图表组件未加载，请刷新页面重试。指标与交易流水仍可查看。";
        element.appendChild(notice);
      });
    }
    resizeCharts();
  }
  new MutationObserver(updateResultState).observe(resultContent, { attributes: true, attributeFilter: ["hidden"] });
  updateResultState();

  function updateBusyState() {
    $("#resultsPanel").setAttribute("aria-busy", String(runButton.disabled));
    $("#runningNotice").hidden = !runButton.disabled;
  }
  new MutationObserver(updateBusyState).observe(runButton, { attributes: true, attributeFilter: ["disabled"] });
  updateBusyState();

  // ECharts must also resize when only the layout changes, not just the window.
  if ("ResizeObserver" in window) {
    const observer = new ResizeObserver(resizeCharts);
    observer.observe($("#navChart"));
    observer.observe($("#fundNavChart"));
  } else {
    window.addEventListener("resize", resizeCharts);
  }
  // Keep the current navigation item aligned with the section being read.
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries) => {
      const entry = entries.filter((item) => item.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
      if (!entry) return;
      const link = links.find((item) => item.getAttribute("href") === `#${entry.target.id}`);
      if (link && link.getAttribute("aria-disabled") !== "true") activateLink(link);
    }, { rootMargin: "-80px 0px -65% 0px", threshold: 0 });
    links.forEach((link) => {
      const target = $(link.getAttribute("href"));
      if (target) observer.observe(target);
    });
  }
})();
