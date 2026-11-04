"""builder 端到端测试：JSON → HTML → 校验通过；非法 JSON 被拒。"""
import json
import os
import subprocess
import sys

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
BUILD_PY = os.path.normpath(os.path.join(SKILL_DIR, "..", "scripts", "build.py"))


def _sample():
    return {
        "title": "selftest 报告",
        "subtitle": "2026-08 | 生成: 2026-08-17",
        "kpis": [{"label": "累计达成", "value": "20.38亿", "change": "vs 预算 -20.0%", "direction": "down"}],
        "insight": "1-5月累计达成20.38亿，低于预算20%。",
        "sections": [
            {"id": "trend", "tab": "趋势", "type": "chart-with-analysis",
             "chart": {"id": "c1", "title": "月度趋势", "valueFormat": "yi:2",
                       "option": {"xAxis": {"type": "category", "data": ["1月", "2月", "3月", "4月", "5月"]},
                                  "yAxis": {"type": "value", "name": "金额(亿)"},
                                  "series": [{"name": "实际", "type": "line",
                                              "data": [235326388, 45844139, 427430907, 472816361, 505206331]}]}},
             "analysis": [{"label": "趋势判断", "color": "blue", "text": "V型反弹，3月恢复。"},
                          {"label": "风险", "color": "pink", "text": "预算持续落后。"}]},
            {"id": "data", "tab": "明细", "type": "table",
             "table": {"title": "明细", "columns": ["月", "达成"],
                       "rows": [["1月", "2.35亿"], ["2月", "0.46亿"]]}}
        ],
        "provenance": {"query": "SELECT 1", "source": "selftest", "skillVersion": "report-generator"}
    }


def test_build_end_to_end(tmp_path):
    jf = tmp_path / "r.json"
    jf.write_text(json.dumps(_sample(), ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([sys.executable, BUILD_PY, "--json", str(jf), "--out", str(tmp_path)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, "build 失败:\n%s\n%s" % (r.stdout, r.stderr)
    htmls = list(tmp_path.glob("report_*.html"))
    assert len(htmls) == 1, "应生成 1 个 HTML: %s" % htmls
    html = htmls[0].read_text(encoding="utf-8")
    assert "__REPORT_VALID__" in html
    for ph in ("{{REPORT_JSON}}", "{{REPORT_TITLE}}", "{{REPORT_META}}", "{{ECHARTS_LIB}}"):
        assert ph not in html
    assert "selftest 报告" in html


def test_build_rejects_invalid_json(tmp_path):
    bad = _sample()
    del bad["provenance"]["query"]  # 删整个 provenance 会命中 validator root 早退，只报 root 级错误
    jf = tmp_path / "bad.json"
    jf.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([sys.executable, BUILD_PY, "--json", str(jf), "--out", str(tmp_path)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode != 0
    assert "provenance.query" in (r.stdout + r.stderr)


def test_build_survives_script_tag_in_text(tmp_path):
    """analysis text 含 </script> 不得撕裂 HTML script 块。"""
    import re as _re
    r = _sample()
    r["sections"][0]["analysis"][0]["text"] = "结论 </script><script>alert(1)</script> 完"
    jf = tmp_path / "s.json"
    jf.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    out = subprocess.run([sys.executable, BUILD_PY, "--json", str(jf), "--out", str(tmp_path)],
                         capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stdout + out.stderr
    html = list(tmp_path.glob("report_*.html"))[0].read_text(encoding="utf-8")
    # 数据段里的 </script> 必须已转义为 <\/（build.py 的 replace("</", "<\\/") 产物）
    assert "<\\/script><script>alert(1)<\\/script>" in html, "转义缺失"
    assert "</script><script>" not in html, "数据段出现裸 </script>，script 块被撕裂"
    # echarts 库 script 之外，渲染 script 段应完整（未被数据内容撕成多段）
    scripts = _re.findall(r"<script>[\s\S]*?</script>", html)
    assert len(scripts) == 2, "script 块数量异常: %d" % len(scripts)
    # round-trip：抽出的 JSON 仍含原始 text
    sys.path.insert(0, os.path.normpath(os.path.join(SKILL_DIR, "..", "scripts")))
    import validate_report as vr
    data = vr.extract_json_from_html(html)
    assert data["sections"][0]["analysis"][0]["text"] == "结论 </script><script>alert(1)</script> 完"


def test_build_bad_json_syntax_graceful(tmp_path):
    jf = tmp_path / "broken.json"
    jf.write_text('{"title": ', encoding="utf-8")
    out = subprocess.run([sys.executable, BUILD_PY, "--json", str(jf), "--out", str(tmp_path)],
                         capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 1
    assert "[FAIL]" in out.stdout and "Traceback" not in out.stdout + out.stderr
    assert not list(tmp_path.glob("report_*.html"))


def test_template_scatter_label_and_item_tooltip_present():
    """模板必须含散点标签自动开启与 item-trigger 单参数 tooltip 分支（静态回归护栏）。"""
    import pathlib
    tpl = (pathlib.Path(SKILL_DIR) / ".." / "templates" / "report-shell.html").resolve()
    src = tpl.read_text(encoding="utf-8")
    assert "labelLayout" in src          # Fix B：散点标签防重叠
    assert "hasExplicitLabel" in src     # Fix B：尊重 JSON 显式 label
    assert "isItemTrigger" in src        # Fix A：item 触发单参数分支
    assert "return p.seriesName" in src  # Fix B：气泡直标产品名


# ---------- v2.2 动态 scope + provenance 隐藏渲染 + 模块可空 ----------

def _sample_simple_ranking():
    """场景A：简单排名——口径 + 结论 + 纯表格，无 KPI 无图表。"""
    return {
        "title": "瓷砖事业部经销商达成 TOP10（2026年10月）",
        "subtitle": "排名 | 生成: 2026-11-03",
        "scope": [
            {"label": "统计期间", "value": "2026年10月"},
            {"label": "指标口径", "value": "含税发货达成额"},
        ],
        "kpis": [],
        "insight": "TOP3 经销商合计贡献 1.83亿，占 TOP10 的 41%。",
        "sections": [
            {"id": "rank", "tab": "排名", "type": "table",
             "table": {"title": "经销商达成 TOP10",
                       "columns": ["排名", "经销商", "达成额"],
                       "rows": [["1", "示例经销商A", "7,692万"],
                                ["2", "示例经销商B", "5,830万"],
                                ["3", "示例经销商C", "4,802万"]]}}
        ],
        "provenance": {"query": "SELECT 1", "source": "selftest"}
    }


def _sample_data_insufficient():
    """场景C：数据不足——只有已确认口径、有限结论与限制说明。"""
    return {
        "title": "华东区渠道毛利分析（数据不足说明）",
        "subtitle": "生成: 2026-11-03",
        "scope": [
            {"label": "统计期间", "value": "2026年10月"},
            {"label": "已确认范围", "value": "仅零售渠道，经销渠道数据未接入"},
        ],
        "kpis": [],
        "insight": "零售渠道 10 月毛利 1,240万（毛利率 28.3%）；经销渠道缺少成本数据，本期无法给出整体毛利判断。",
        "sections": [],
        "provenance": {"query": "SELECT 1", "source": "selftest",
                       "limitations": ["经销渠道成本数据未接入，毛利结论仅覆盖零售渠道"]}
    }


def _build(tmp_path, payload, tag):
    jf = tmp_path / ("%s.json" % tag)
    jf.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([sys.executable, BUILD_PY, "--json", str(jf), "--out", str(tmp_path)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, "build 失败:\n%s\n%s" % (r.stdout, r.stderr)
    return list(tmp_path.glob("report_*.html"))[0].read_text(encoding="utf-8")


def test_build_simple_ranking_scope_table_only(tmp_path):
    """场景A：空 KPI + 纯表格 + scope，全链路构建通过。"""
    html = _build(tmp_path, _sample_simple_ranking(), "simple")
    assert "__REPORT_VALID__" in html


def test_build_data_insufficient_empty_sections(tmp_path):
    """场景C：sections 空数组，构建通过且不出空 Tab。"""
    html = _build(tmp_path, _sample_data_insufficient(), "insufficient")
    assert "__REPORT_VALID__" in html
    assert "tab-nav" in html  # 容器在，运行时空数组走隐藏分支


def test_build_old_json_without_scope_still_works(tmp_path):
    """场景D：旧版 report.json（无 scope）兼容，不报错。"""
    html = _build(tmp_path, _sample(), "legacy")
    assert "__REPORT_VALID__" in html
    assert '"scope"' not in html


def test_build_full_provenance_preserved_but_not_rendered(tmp_path):
    """场景E：完整审计数据内嵌保留，正文不出现技术追溯面板。"""
    r = _sample()
    r["scope"] = [{"label": "统计期间", "value": "2026年1-5月"}]
    r["provenance"] = {
        "query": "SELECT org, SUM(amt) FROM demo_sales GROUP BY org",
        "source": "demo.dws_demo_f", "skillVersion": "sales-performance-knowledge v3",
        "lastUpdate": "2026-06-01",
        "filters": ["期间=2026年1-5月", "组织=瓷砖事业部"],
        "limitations": ["示例数据"], "dataQuality": ["无空值"],
    }
    html = _build(tmp_path, r, "prov")
    # 可见面板移除
    assert "provenance-section" not in html
    assert "数据来源与追溯" not in html
    # 审计数据完整内嵌（var data = ... 内保留，供 extract_json_from_html 复原）
    sys.path.insert(0, os.path.normpath(os.path.join(SKILL_DIR, "..", "scripts")))
    import validate_report as vr
    data = vr.extract_json_from_html(html)
    assert data["provenance"]["query"] == r["provenance"]["query"]
    assert data["provenance"]["skillVersion"] == r["provenance"]["skillVersion"]
    assert data["provenance"]["filters"] == r["provenance"]["filters"]
    assert data["scope"] == r["scope"]
    assert "__REPORT_VALID__" in html


def test_template_scope_layout_and_no_visible_provenance():
    """模板静态回归：scope 在 insight/KPI 之前；provenance 可见渲染移除；scope 渲染走 escapeHTML。"""
    import pathlib
    src = (pathlib.Path(SKILL_DIR) / ".." / "templates" / "report-shell.html").resolve().read_text(encoding="utf-8")
    # 顺序：标题 → scope → insight → KPI
    assert src.index('class="report-scope"') < src.index('class="insight-banner"')
    assert src.index('class="insight-banner"') < src.index('class="kpi-section"')
    # provenance 可见 DOM/CSS/JS 已移除，VALID 标记保留
    assert "provenance-section" not in src
    assert "provSection" not in src
    assert "__REPORT_VALID__" in src
    # scope 渲染：label/value 均转义；空/缺失走隐藏分支
    assert "escapeHTML(String(item.label))" in src
    assert "escapeHTML(String(item.value))" in src
    assert "scopeBar.style.display = 'none'" in src


def test_skill_md_principles_present():
    """SKILL.md 静态护栏：六原则、归因分级、业务限制披露规则不得在后续编辑中静默丢失。"""
    import pathlib
    src = (pathlib.Path(SKILL_DIR) / ".." / "SKILL.md").resolve().read_text(encoding="utf-8")
    # 六原则标题齐全
    for title in ("以业务问题决定报告内容", "口径先行", "结论由数据驱动", "图表按需生成",
                  "分析深度自适应", "审计完整保留"):
        assert title in src, "缺少原则: %s" % title
    # 归因可信度分级（数据事实/分析推断/已验证原因），未验证归因不得写成确定事实
    for kw in ("数据事实", "分析推断", "已验证原因", "季末结算", "不得写成确定事实", "不编造根因"):
        assert kw in src, "缺少归因分级关键词: %s" % kw
    # 业务限制披露：影响经营判断才披露、不整段搬运、不硬造
    for kw in ("影响经营判断", "未做同比", "指标不可比", "不整段搬运", "不硬造风险提示"):
        assert kw in src, "缺少限制披露关键词: %s" % kw
