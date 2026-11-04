#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_report.py — REPORT_JSON v2 纯JSON协议校验器（零依赖，Python 3.9+）。

用法:
    python validate_report.py <report.json | report.html>

校验层:
    1. JSON 可解析（HTML 输入先抽 var data = ... 段）
    2. 结构校验（手写校验器，规则同 references/report-schema.json）
    3. 黑名单：eval( / function( 旧函数串
    4. 占位符残留（HTML 输入）
    5. 结构补充：chart 必须有 valueFormat、section id 唯一
    6. scope 动态口径：label/value 非空字符串，拦截 SQL 片段/内部表名/凭据
    7. 大小：单 chart 数据点 <= 200、HTML <= 5MB
    8. 内联 JS 语法（node 存在则 --check，否则跳过）

动态性说明: kpis/sections 可为空数组（按实际问题取舍，不凑模块）；
图表 section 不强制存在（纯排名表/数据不足报告合法）。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

VALUE_FORMAT_RE = re.compile(r"^(yi|wan|percent|signed_percent|sqm_wan|yuan|int)(:[0-9])?$")
FUNC_BLACKLIST = re.compile(r"function\s*\(|\beval\s*\(")
# scope 口径文本拦截：SQL 语句形态 / snake_case 内部表名字段名 / 凭据键值
SCOPE_SQL_RE = re.compile(
    r"(?is)\b(select\s+.{1,200}?\s+from|insert\s+into|delete\s+from|update\s+\S+\s+set"
    r"|group\s+by|order\s+by|left\s+join|right\s+join|inner\s+join|full\s+join"
    r"|where\s+\S+\s*(=|like|in|>)\b)\b")
SCOPE_TECH_TOKEN_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
SCOPE_CREDENTIAL_RE = re.compile(
    r"(?i)(password|passwd|api[_-]?key|apikey|secret|token)\s*[=:：]\s*\S+|sk-[A-Za-z0-9]{16,}")
PLACEHOLDERS = ("{{REPORT_JSON}}", "{{REPORT_TITLE}}", "{{REPORT_META}}", "{{ECHARTS_LIB}}")
MAX_DATA_POINTS = 200
HTML_SIZE_LIMIT = 5 * 1024 * 1024


def validate_data(data):
    """校验已解析的 REPORT_JSON dict，返回错误字符串列表（空=通过）。"""
    errs = []

    def err(path, msg):
        errs.append("[%s] %s" % (path, msg))

    if not isinstance(data, dict):
        return ["[root] 报告必须是 JSON object"]
    for k in ("title", "kpis", "insight", "sections", "provenance"):
        if k not in data:
            err("root", "缺少必填字段 %s" % k)
    if errs:
        return errs
    if not str(data.get("title") or "").strip():
        err("title", "不能为空")
    if not str(data.get("insight") or "").strip():
        err("insight", "不能为空")

    _validate_scope(data, err)

    kpis = data.get("kpis")
    if not isinstance(kpis, list):
        err("kpis", "必须是数组（无 KPI 时给空数组，不凑数）")
    else:
        for i, k in enumerate(kpis):
            if not isinstance(k, dict):
                err("kpis[%d]" % i, "必须是 object")
                continue
            if not str(k.get("label") or "").strip():
                err("kpis[%d].label" % i, "不能为空")
            if not str(k.get("value") or "").strip():
                err("kpis[%d].value" % i, "不能为空")
            if k.get("direction") is not None and k["direction"] not in ("up", "down", "neutral"):
                err("kpis[%d].direction" % i, "非法值 %r，允许 up/down/neutral" % k["direction"])

    sections = data.get("sections")
    seen_ids = set()
    if not isinstance(sections, list):
        err("sections", "必须是数组（无图表/明细内容时给空数组）")
        sections = []
    for i, s in enumerate(sections):
        p = "sections[%d]" % i
        if not isinstance(s, dict):
            err(p, "必须是 object")
            continue
        sid = s.get("id")
        if not str(sid or "").strip():
            err(p + ".id", "不能为空")
        elif not isinstance(sid, str):
            err(p + ".id", "必须是字符串")
        else:
            if sid in seen_ids:
                err(p + ".id", "重复 id %r" % sid)
            seen_ids.add(sid)
        if not str(s.get("tab") or "").strip():
            err(p + ".tab", "不能为空")
        stype = s.get("type")
        if stype not in ("chart-with-analysis", "table"):
            err(p + ".type", "非法值 %r，允许 chart-with-analysis/table" % stype)
            continue
        if stype == "chart-with-analysis":
            _validate_chart_section(s, p, err)
        else:
            _validate_table_section(s, p, err)

    prov = data.get("provenance")
    if not isinstance(prov, dict):
        err("provenance", "必须是 object")
    else:
        if not str(prov.get("query") or "").strip():
            err("provenance.query", "必填非空（SQL，用于审计）")

    _scan_blacklist(data, "$", errs)
    return errs


def _validate_scope(data, err):
    """scope：动态口径数组，可缺失/可为空数组。

    条目 label/value 必须是非空字符串，且面向业务表达——
    拦截 SQL 片段、内部表名/字段名（snake_case）、凭据类敏感信息。
    不硬编码任何业务口径标签（label 由 AI 按问题自定）。"""
    scope = data.get("scope")
    if scope is None:
        return
    if not isinstance(scope, list):
        err("scope", "必须是数组（label/value 口径条目）")
        return
    for i, item in enumerate(scope):
        p = "scope[%d]" % i
        if not isinstance(item, dict):
            err(p, "必须是 object（含 label/value）")
            continue
        for f in ("label", "value"):
            v = item.get(f)
            if not isinstance(v, str) or not v.strip():
                err("%s.%s" % (p, f), "必须是非空字符串（无意义的空条目不要写）")
                continue
            if SCOPE_SQL_RE.search(v):
                err("%s.%s" % (p, f), "不得包含 SQL 片段（口径用业务语言描述）")
            if SCOPE_TECH_TOKEN_RE.search(v):
                err("%s.%s" % (p, f), "不得混入内部表名/字段名（snake_case 技术标识）")
            if SCOPE_CREDENTIAL_RE.search(v):
                err("%s.%s" % (p, f), "不得包含凭据等敏感信息")


def _validate_chart_section(s, p, err):
    ch = s.get("chart")
    charts = ch if isinstance(ch, list) else ([ch] if ch else [])
    if not charts:
        err(p + ".chart", "chart-with-analysis 必须有 chart")
    for j, c in enumerate(charts):
        cp = p + (".chart[%d]" % j if isinstance(ch, list) else ".chart")
        if not isinstance(c, dict):
            err(cp, "必须是 object")
            continue
        if not str(c.get("id") or "").strip():
            err(cp + ".id", "不能为空")
        if not str(c.get("title") or "").strip():
            err(cp + ".title", "不能为空")
        vf = c.get("valueFormat")
        if not vf:
            err(cp + ".valueFormat", "必填（yi/wan/percent/signed_percent/sqm_wan/yuan/int，:N 小数位）")
        elif not isinstance(vf, str) or not VALUE_FORMAT_RE.match(vf):
            err(cp + ".valueFormat", "非法值 %r，允许 yi/wan/percent/signed_percent/sqm_wan/yuan/int 可带 :N" % vf)
        tt = c.get("tooltipTemplate")
        if tt is not None and tt not in ("multi", "pie"):
            err(cp + ".tooltipTemplate", "非法值 %r，允许 multi/pie" % tt)
        opt = c.get("option")
        if not isinstance(opt, dict):
            err(cp + ".option", "必须是 object")
        else:
            n = _count_data_points(opt)
            if n > MAX_DATA_POINTS:
                err(cp + ".option", "数据点 %d 超上限 %d（先聚合再报告）" % (n, MAX_DATA_POINTS))
            for si, se in enumerate(opt.get("series") or []):
                if isinstance(se, dict):
                    svf = se.get("valueFormat")
                    if svf is not None and (not isinstance(svf, str) or not VALUE_FORMAT_RE.match(svf)):
                        err(cp + ".option.series[%d].valueFormat" % si,
                            "非法值 %r，允许 yi/wan/percent/signed_percent/sqm_wan/yuan/int 可带 :N" % svf)
                    if se.get("type") == "scatter":
                        sdata = se.get("data") or []
                        named = sum(1 for dp in sdata if isinstance(dp, dict) and dp.get("name"))
                        if named >= 2:
                            err(cp + ".option.series[%d]" % si,
                                "散点含 %d 个命名点，应拆分为每产品独立 series（每个 series 一个数据点）" % named)
            yax = opt.get("yAxis")
            ax_list = yax if isinstance(yax, list) else ([yax] if yax else [])
            for yi_, ax in enumerate(ax_list):
                if isinstance(ax, dict):
                    avf = ax.get("valueFormat")
                    if avf is not None and (not isinstance(avf, str) or not VALUE_FORMAT_RE.match(avf)):
                        ax_path = ("yAxis[%d]" % yi_) if isinstance(yax, list) else "yAxis"
                        err(cp + ".option." + ax_path + ".valueFormat",
                            "非法值 %r，允许 yi/wan/percent/signed_percent/sqm_wan/yuan/int 可带 :N" % avf)
    ana = s.get("analysis")
    if not isinstance(ana, list) or not ana:
        err(p + ".analysis", "chart-with-analysis 必须有非空 analysis[]")
    else:
        for k, a in enumerate(ana):
            ap = "%s.analysis[%d]" % (p, k)
            if not isinstance(a, dict):
                err(ap, "必须是 object")
                continue
            for f in ("label", "text"):
                if not str(a.get(f) or "").strip():
                    err(ap + "." + f, "不能为空")
            if a.get("color") not in ("blue", "pink", "cyan"):
                err(ap + ".color", "非法值 %r，允许 blue/pink/cyan" % a.get("color"))


def _validate_table_section(s, p, err):
    tbl = s.get("table")
    if not isinstance(tbl, dict):
        err(p + ".table", "table 类型必须有嵌套 table 对象（扁平式已废弃）")
        return
    if not isinstance(tbl.get("columns"), list) or not tbl["columns"]:
        err(p + ".table.columns", "必须是非空数组")
    if not isinstance(tbl.get("rows"), list) or not tbl["rows"]:
        err(p + ".table.rows", "必须是非空数组")
    rows = tbl["rows"] if isinstance(tbl.get("rows"), list) else []
    ps = tbl.get("pageSize")
    if ps is not None and (isinstance(ps, bool) or not isinstance(ps, int) or ps < 1):
        err(p + ".table.pageSize", "必须是 >=1 的整数")
    for ri, row in enumerate(rows):
        if not isinstance(row, list):
            err(p + ".table.rows[%d]" % ri, "必须是数组")
            continue
        for ci, cell in enumerate(row):
            if isinstance(cell, dict):
                v_val = cell.get("v")
                if not isinstance(v_val, str) or not v_val.strip():
                    err(p + ".table.rows[%d][%d].v" % (ri, ci), "必须是非空字符串")
                if cell.get("tone") not in ("good", "warn", "bad", "na"):
                    err(p + ".table.rows[%d][%d].tone" % (ri, ci),
                        "非法值 %r，允许 good/warn/bad/na" % cell.get("tone"))
            elif not isinstance(cell, (str, int, float)) or isinstance(cell, bool):
                err(p + ".table.rows[%d][%d]" % (ri, ci), "单元格必须是字符串/数值或 {v, tone} 对象")


def _count_data_points(opt):
    n = 0
    for s_ in opt.get("series", []) or []:
        if isinstance(s_, dict) and isinstance(s_.get("data"), list):
            n += len(s_["data"])
    return n


def _scan_blacklist(obj, path, errs):
    """递归扫描字符串值里的旧函数格式。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("valueFormat", "tooltipTemplate"):
                continue  # 已由专门规则校验
            _scan_blacklist(v, "%s.%s" % (path, k), errs)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _scan_blacklist(v, "%s[%d]" % (path, i), errs)
    elif isinstance(obj, str):
        if FUNC_BLACKLIST.search(obj):
            errs.append("[%s] 旧函数格式已废弃（%r...）→ 改用 valueFormat 声明" % (path, obj[:40]))


def validate_html(html, node_check=True):
    """校验已生成的 HTML：占位符残留 + 大小 + VALID 标记 + 内联 JS 语法。"""
    errs = []
    for ph in PLACEHOLDERS:
        if ph in html:
            errs.append("[html] 占位符 %s 未替换" % ph)
    if len(html.encode("utf-8")) > HTML_SIZE_LIMIT:
        errs.append("[html] 大小 %.1fMB 超上限 5MB" % (len(html.encode("utf-8")) / 1048576))
    if "__REPORT_VALID__" not in html:
        errs.append("[html] 缺少 __REPORT_VALID__ 标记（模板过旧或渲染脚本被破坏）")
    if node_check and shutil.which("node"):
        m = re.search(r"<script>\s*(\(function\(\)\s*\{.*?\}\)\(\);?)\s*</script>\s*</body>", html, re.S)
        inline_js = m.group(1) if m else ""
        if inline_js:
            fd, tmp = tempfile.mkstemp(suffix=".js")
            try:
                os.write(fd, inline_js.encode("utf-8"))
                os.close(fd)
                p = subprocess.run(["node", "--check", tmp], capture_output=True)
                if p.returncode != 0:
                    errs.append("[html] 内联 JS 语法错误: %s"
                                % p.stderr.decode("utf-8", "ignore")[:200])
            finally:
                os.unlink(tmp)
    return errs


def extract_json_from_html(html):
    """从 HTML 抽 var data = {...}; 段（json.dumps 单行产物，行内唯一分号在末尾）。"""
    m = re.search(r"var data = (\{.*\});", html)
    if not m:
        raise ValueError("HTML 中找不到 var data = ... 段")
    return json.loads(m.group(1))


def main(argv=None):
    ap = argparse.ArgumentParser(description="REPORT_JSON v2 校验器")
    ap.add_argument("target", help="report.json 或已生成的 report.html")
    ap.add_argument("--no-node", action="store_true", help="跳过 node 语法检查")
    args = ap.parse_args(argv)

    with open(args.target, "r", encoding="utf-8") as f:
        content = f.read()

    if args.target.endswith(".json"):
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            print("[FAIL] JSON 解析失败: %s" % e)
            return 1
        errs = validate_data(data)
    else:
        try:
            data = extract_json_from_html(content)
        except (ValueError, json.JSONDecodeError) as e:
            print("[FAIL] 抽取 REPORT_JSON 失败: %s" % e)
            return 1
        errs = validate_data(data) + validate_html(content, node_check=not args.no_node)

    if errs:
        for e in errs:
            print("[FAIL] " + e)
        print("")
        print("共 %d 个错误" % len(errs))
        return 1
    print("VALIDATION PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
