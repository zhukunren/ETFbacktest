"""UI regression tests with deterministic API responses; no live market calls.

Run: python -m pip install pytest playwright
     python -m playwright install chromium
     python -m pytest tests/test_frontend.py -q
Set UI_CHROMIUM_PATH to use a system Chromium binary.
The ECharts test double checks integration/resize calls, not canvas rendering.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil

import pytest

pw = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parents[1]
FUND = {"code": "510500", "name": "中证500ETF"}
RESULT = {
    "meta": {"start_date": "2023-09-23", "end_date": "2026-09-23", "price_basis": "日收盘价"},
    "metrics": {"final_value": 126800, "profit": 26800, "capital_return": .268,
                "invested_capital": 100000, "annualized_return": .0821,
                "max_drawdown": -.1126, "annualized_volatility": .143,
                "time_weighted_return": .268, "trading_days": 730,
                "total_fees": 362.8, "trade_count": 2, "sharpe": .574},
    "series": {"dates": ["2023-09-23", "2026-09-23"], "nav": [100000, 126800],
               "invested": [100000, 100000],
               "fund_nav": {"base_date": "2023-09-23", "items": [
                   {"code": "510300", "name": "沪深300ETF", "values": [1, 1.21]},
                   {"code": "518880", "name": "黄金ETF", "values": [1, 1.35]}]}},
    "allocation": [
        {"code": "510300", "name": "沪深300ETF", "target_weight": .6, "actual_weight": .59,
         "relative_nav": 1.21, "period_return": .21, "value": 74812},
        {"code": "518880", "name": "黄金ETF", "target_weight": .4, "actual_weight": .41,
         "relative_nav": 1.35, "period_return": .35, "value": 51988}],
    "trades": [
        {"date": "2026-09-01", "code": "510300", "side": "buy", "shares": 200,
         "price": 4.21, "gross_value": 842, "fee": .2526, "reason": "定期再平衡"},
        {"date": "2026-09-01", "code": "518880", "side": "sell", "shares": 100,
         "price": 8.42, "gross_value": 842, "fee": .2526, "reason": "定期再平衡"}],
}
# The real app.js is exercised unchanged. This spy isolates CDN access.
CHART_SPY = """
(() => {
  const instances = new Map();
  window.__chartEvents = [];
  window.echarts = {
    init(el) {
      const instance = {
        setOption(option) { window.__chartEvents.push({type: 'option', id: el.id, series: option.series.length}); },
        resize() { window.__chartEvents.push({type: 'resize', id: el.id, width: el.clientWidth}); },
        dispose() { instances.delete(el); window.__chartEvents.push({type: 'dispose', id: el.id}); }
      };
      instances.set(el, instance);
      return instance;
    },
    getInstanceByDom(el) { return instances.get(el); }
  };
})();
"""


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        path = os.environ.get("UI_CHROMIUM_PATH") or shutil.which("chromium")
        options = {"headless": True, "args": ["--no-sandbox"]}
        if path:
            options["executable_path"] = path
        browser = playwright.chromium.launch(**options)
        yield browser
        browser.close()


API_STUB = r"""
window.__api = {
  requests: [], pending: [], hold: false, error: null,
  response(data, ok = true) { return {ok, json: async () => structuredClone(data)}; },
  complete() { this.pending.shift()(this.response(this.result)); }
};
window.fetch = async (url, options = {}) => {
  const api = window.__api;
  api.requests.push({url, body: options.body ? JSON.parse(options.body) : null});
  if (url === '/api/catalog/status') return api.response({count: 3, source: 'local'});
  if (url === '/api/catalog/refresh') return api.response({count: 4, source: 'akshare'});
  if (url.startsWith('/api/etfs/search?')) return api.response({items: [{code: '510500', name: '中证500ETF'}]});
  if (url === '/api/backtest') {
    if (api.hold) return new Promise(resolve => api.pending.push(resolve));
    if (api.error) return api.response({detail: api.error}, false);
    return api.response(api.result);
  }
  throw new Error(`Unexpected API request: ${url}`);
};
"""


def load_workspace(page):
    """Render repository files directly: no server, navigation or network needed."""
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    css = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
    html = re.sub(r'<script\b[^>]*src=[^>]*></script>', '', html)
    html = re.sub(r'<link\b[^>]*>', '', html)
    html = html.replace('/static/dongwu-logo.png', 'data:image/png;base64,invalid')
    html = html.replace('</head>', f'<style>{css}</style></head>')
    page.set_content(html)
    page.add_script_tag(content=CHART_SPY)
    page.add_script_tag(content=API_STUB)
    page.evaluate("result => { window.__api.result = result; }", RESULT)
    page.add_script_tag(content="window.lucide={createIcons(){}};")
    for name in ["app.js", "workspace.js"]:
        page.add_script_tag(content=(ROOT / "app/static" / name).read_text(encoding="utf-8"))


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    load_workspace(page)
    pw.expect(page.locator("#selectedCount")).to_have_text("2")
    yield page
    assert not errors, errors
    context.close()


def test_dom_contract():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    ids = re.findall(r'\bid="([\w-]+)"', html)
    assert len(ids) == len(set(ids)), "Duplicate DOM ids"
    required = set(re.findall(r'\$\("#([\w-]+)"\)', js))
    assert required <= set(ids), required - set(ids)
    assert len(re.findall(r"<h1\b", html)) == 1
    assert '/static/workspace.js' in html


def test_initial_state_and_catalog(page):
    pw.expect(page.locator("#resultContent")).to_be_hidden()
    pw.expect(page.locator("#emptyState")).to_be_visible()
    pw.expect(page.locator("#weightTotal")).to_have_text("100.00%")
    pw.expect(page.locator("#weightHint")).to_have_text("权重已就绪")
    pw.expect(page.locator(".brand-logo")).to_have_class(re.compile("has-fallback"))
    pw.expect(page.locator("#catalogCount")).to_have_text("3 只")
    page.locator("#refreshCatalog").click()
    pw.expect(page.locator("#catalogCount")).to_have_text("4 只")
    pw.expect(page.locator("#sourceState")).to_have_class(re.compile("is-ready"))


def test_search_add_remove_and_validation(page):
    page.locator("#fundSearch").fill("510500")
    page.locator("[data-add-code='510500']").click()
    pw.expect(page.locator("#selectedCount")).to_have_text("3")
    pw.expect(page.locator("#weightTrack > span")).to_have_count(3)
    page.locator("[data-remove-code='510500']").click()
    pw.expect(page.locator("#selectedCount")).to_have_text("2")
    page.locator("[data-weight-code='510300']").fill("70")
    pw.expect(page.locator("#weightTotal")).to_have_text("120.00%")
    pw.expect(page.locator("#weightTotal")).to_have_class("is-invalid")
    page.locator("#runBacktest").click()
    pw.expect(page.locator("#toast")).to_contain_text("100%")
    pw.expect(page.locator("#resultContent")).to_be_hidden()
    page.locator("#equalizeWeights").click()
    pw.expect(page.locator("#weightTotal")).to_have_text("100.00%")
    pw.expect(page.locator("#weightHint")).to_have_text("权重已就绪")


def test_dca_payload_loading_and_results(page):
    page.evaluate("window.__api.hold = true")
    page.locator("#dcaTab").click()
    pw.expect(page.locator("#dcaSettings")).to_be_visible()
    pw.expect(page.locator("#rebalanceSettings")).to_be_hidden()
    page.locator("#dcaMode").select_option("shares")
    pw.expect(page.locator("#dcaValueLabel")).to_have_text("每只基金每期份额")
    page.locator("#dcaFrequency").select_option("weekly_end")
    page.locator("#startDate").fill("2023-09-23")
    page.locator("#endDate").fill("2026-09-23")
    page.locator("#runBacktest").click()
    pw.expect(page.locator("#runBacktest")).to_be_disabled()
    pw.expect(page.locator("#runningNotice")).to_be_visible()
    pw.expect(page.locator("#resultsPanel")).to_have_attribute("aria-busy", "true")
    assert page.evaluate("window.__api.pending.length") == 1
    payload = page.evaluate("window.__api.requests.find(r => r.url === '/api/backtest').body")
    assert payload == {
        "holdings": [{"code": "510300", "name": "沪深300ETF", "weight": 60},
                     {"code": "518880", "name": "黄金ETF", "weight": 40}],
        "start_date": "2023-09-23", "end_date": "2026-09-23", "initial_capital": 100000,
        "strategy": "dca", "rebalance_frequency": "none", "dca_frequency": "weekly_end",
        "dca_mode": "shares", "dca_value": 100, "fee_rate": .0003,
    }
    page.evaluate("window.__api.complete()")
    pw.expect(page.locator("#resultTitle")).to_have_text("定投计划结果")
    pw.expect(page.locator("#resultContent")).to_be_visible()
    pw.expect(page.locator("#runningNotice")).to_be_hidden()
    pw.expect(page.locator("#resultsPanel")).to_have_attribute("aria-busy", "false")
    pw.expect(page.locator("#metricCapitalReturn")).to_have_text("26.80%")
    pw.expect(page.locator("#metricCapitalReturn")).to_have_class("positive")
    pw.expect(page.locator("#metricDrawdown")).to_have_class("negative")
    pw.expect(page.locator("#tradesBody tr")).to_have_count(2)
    pw.expect(page.locator("#allocationBody tr")).to_have_count(2)
    pw.expect(page.locator("[href='#tradesSection']")).to_have_attribute("aria-disabled", "false")
    page.wait_for_function("window.__chartEvents.filter(e => e.type === 'option').length === 2")


def test_focus_and_chart_resize(page):
    page.locator("#runBacktest").click()
    pw.expect(page.locator("#resultContent")).to_be_visible()
    before = page.locator("#navChart").bounding_box()["width"]
    page.locator("#toggleConfiguration").click()
    pw.expect(page.locator("#configurationPanel")).to_be_hidden()
    pw.expect(page.locator("#toggleConfiguration")).to_have_attribute("aria-expanded", "false")
    assert page.locator("#navChart").bounding_box()["width"] > before
    page.wait_for_function("window.__chartEvents.some(e => e.type === 'resize' && e.width > 1000)")
    page.locator(".main-nav [href='#configurationPanel']").click()
    pw.expect(page.locator("#configurationPanel")).to_be_visible()
    pw.expect(page.locator("#fundSearch")).to_be_focused()
    page.locator("#toggleConfiguration").click()
    page.set_viewport_size({"width": 390, "height": 844})
    pw.expect(page.locator("#configurationPanel")).to_be_visible()
    page.set_viewport_size({"width": 1440, "height": 900})
    pw.expect(page.locator("#toggleConfiguration")).to_have_attribute("aria-expanded", "true")


def test_error_recovery_and_unavailable_navigation(page):
    page.locator("[href='#tradesSection']").dispatch_event("click")
    pw.expect(page.locator("#runBacktest")).to_be_focused()
    page.evaluate("window.__api.error = '测试：无共同交易日'")
    page.locator("#runBacktest").click()
    pw.expect(page.locator("#toast")).to_contain_text("无共同交易日")
    pw.expect(page.locator("#runBacktest")).to_be_enabled()
    pw.expect(page.locator("#runningNotice")).to_be_hidden()
    pw.expect(page.locator("#emptyState")).to_be_visible()


@pytest.mark.parametrize("width", [320, 390, 600, 768, 980, 1024, 1250, 1280, 1440, 1920])
def test_responsive_layout(page, width):
    page.set_viewport_size({"width": width, "height": 900})
    for result in [False, True]:
        if result:
            page.locator("#runBacktest").click()
            pw.expect(page.locator("#resultContent")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (width, result)
        for selector in ["#configurationPanel", "#resultsPanel", "#runBacktest"]:
            box = page.locator(selector).bounding_box()
            assert box["x"] >= 0 and box["x"] + box["width"] <= width + 1, (width, selector, box)
    if width >= 981:
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(400)
        box = page.locator("#runBacktest").bounding_box()
        assert box["y"] + box["height"] < 900, ("Run action below fold", width, box)


def test_reduced_motion(page):
    page.emulate_media(reduced_motion="reduce")
    assert page.evaluate("getComputedStyle(document.documentElement).scrollBehavior") == "auto"


def test_empty_portfolio(page):
    for code in ["510300", "518880"]:
        page.locator(f"[data-remove-code='{code}']").click()
    pw.expect(page.locator("#selectedCount")).to_have_text("0")
    pw.expect(page.locator("#weightTrack > span")).to_have_count(0)
    page.locator("#runBacktest").click()
    pw.expect(page.locator("#toast")).to_contain_text("请至少添加一只 ETF")


def test_cdn_failure_does_not_break_metrics(page):
    page.evaluate("window.echarts = undefined")
    page.locator("#runBacktest").click()
    pw.expect(page.locator("#metricCapitalReturn")).to_have_text("26.80%")
    pw.expect(page.locator("#navChart .chart-unavailable")).to_be_visible()
    page.locator("#toggleConfiguration").click()
    pw.expect(page.locator("#configurationPanel")).to_be_hidden()
