import gradio as gr
import pandas as pd
import plotly.graph_objects as go

from app.analysis import consolidation, supplier360
from app.ingest.pipeline import datasets_overview
from app.ingest.xlsx import ingest_file
from app.llm import client as llm
from app.market import store as market

CSS = """
footer {display: none !important}
.gradio-container {font-family: "Inter", "PingFang SC", "Microsoft YaHei", sans-serif}
.tab-nav button {font-weight: 600}
.card {background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 12px; padding: 14px}
.muted {color: #64748B; font-size: 12px}
"""

EMPTY_DF = pd.DataFrame()

DS_COLS = {
    "dataset_key": "类型",
    "label": "名称",
    "file_name": "文件",
    "rows_loaded": "载入行数",
    "rows_quarantined": "异常标记",
    "imported_at": "导入时间",
    "status": "状态",
}


def _ds_frame() -> pd.DataFrame:
    rows = datasets_overview()
    if not rows:
        return EMPTY_DF
    return pd.DataFrame(rows).rename(columns=DS_COLS)[list(DS_COLS.values())]


def _fmt_report(reports: list[dict]) -> str:
    blocks = []
    for r in reports:
        head = f"<b>{r['label']}</b> — {'重复文件，跳过' if r['status'] == 'duplicate' else '导入成功'}"
        body = r.get("note") or (
            f"载入 {r['rows_loaded']:,} 行"
            + (f"，{r['rows_quarantined']:,} 行存在异常字段（已置空但仍参与汇总）"
               if r.get("rows_quarantined") else "")
        )
        checks = ""
        if r.get("checks"):
            rows = "".join(
                f"<tr><td style='padding:2px 10px'>{c['check']}</td>"
                f"<td style='padding:2px 10px'><b>{c['value']}</b></td>"
                f"<td style='padding:2px 10px;color:#64748B'>{c['note']}</td></tr>"
                for c in r["checks"]
            )
            checks = (
                "<table style='font-size:12px;border-collapse:collapse;margin-top:6px'>"
                "<tr style='color:#64748B'><td style='padding:2px 10px'>体检项</td>"
                f"<td style='padding:2px 10px'>结果</td><td style='padding:2px 10px'>说明</td></tr>"
                f"{rows}</table>"
            )
        blocks.append(
            f"<div class='card' style='margin-bottom:10px'>{head}<div class='muted' "
            f"style='margin-top:4px'>{body}</div>{checks}</div>"
        )
    return "".join(blocks) or "未选择文件"


def do_upload(files):
    reports = []
    for f in files or []:
        name = str(f.name).replace("\\", "/").split("/")[-1]
        try:
            reports.append(ingest_file(f.name, name))
        except Exception as e:
            reports.append(
                {
                    "label": name,
                    "status": "error",
                    "note": f"导入失败：{e}",
                    "rows_loaded": 0,
                    "rows_quarantined": 0,
                    "checks": [],
                }
            )
    return (
        _fmt_report(reports),
        _ds_frame(),
        gr.update(choices=supplier360.vendor_options()),
        gr.update(choices=supplier360.material_options()),
    )


def on_vendor(vendor):
    if not vendor:
        return "", EMPTY_DF, EMPTY_DF, EMPTY_DF, EMPTY_DF
    return (
        supplier360.profile_html(vendor),
        supplier360.overview(vendor),
        supplier360.price_position(vendor),
        supplier360.po_performance(vendor),
        supplier360.rr_lookup(vendor),
    )


def on_material(material):
    if not material:
        return EMPTY_DF
    return supplier360.cross_plant(material)


def on_scan():
    df = consolidation.scan()
    return consolidation.kpis_html(), df if not df.empty else EMPTY_DF


def on_segment_select(evt: gr.SelectData, df: pd.DataFrame):
    if df is None or df.empty or evt.index is None:
        return EMPTY_DF, EMPTY_DF
    seg = df.iloc[evt.index[0]]["支出段"]
    d = consolidation.detail(seg)
    c = consolidation.cbcs_table(consolidation.vendors_in_segment(seg))
    return d if not d.empty else EMPTY_DF, c if not c.empty else EMPTY_DF


def on_market_refresh():
    df, err = market.refresh()
    note = (
        f"<div class='card' style='border-color:#FED7AA'>{err}</div>"
        if err
        else "<div class='card'>TradingEconomics 抓取成功，已写入快照。</div>"
    )
    note += f"<div class='muted' style='margin-top:6px'>{market.source_note()}</div>"
    return df, market.alerts(df), gr.update(choices=market.commodity_options()), note


def on_commodity(commodity):
    if not commodity:
        return None, "请选择商品"
    h = market.history(commodity)
    if h.empty:
        return None, f"{commodity}：暂无历史数据"
    fig = go.Figure(
        go.Scatter(
            x=pd.to_datetime(h["date"]),
            y=pd.to_numeric(h["price"], errors="coerce"),
            mode="lines",
            line={"color": "#185FA5", "width": 2},
        )
    )
    fig.update_layout(
        title=f"{commodity}（来源：{h['source'].iloc[0]}）",
        margin={"l": 40, "r": 20, "t": 40, "b": 30},
        height=340,
        template="plotly_white",
    )
    return fig, market.history_stats(commodity)


def _on_load():
    return (
        _ds_frame(),
        gr.update(choices=supplier360.vendor_options()),
        gr.update(choices=supplier360.material_options()),
    )


def build_blocks() -> gr.Blocks:
    with gr.Blocks(title="Sourcing AI") as demo:
        gr.HTML(
            "<div style='display:flex;align-items:baseline;gap:12px'>"
            "<h1 style='margin:0;font-size:22px'>Sourcing AI</h1>"
            "<span class='muted'>智能寻源助手 · 供应商360 / 品类整合 / 市场监测 · "
            "每个数字可追溯来源</span></div>"
        )
        with gr.Tabs():
            with gr.Tab("📤 数据管理"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.HTML(
                            "<div class='card'><b>上传数据</b><div class='muted' "
                            "style='margin-top:6px'>支持 CSV（≥100MB 秒级解析）与 RapidRatings "
                            "xlsx，自动识别 8 类文件。重复文件自动跳过，增量按主键 UPSERT，"
                            "异常价格行进隔离区不参与计算。</div></div>"
                        )
                        files = gr.File(label="选择文件", file_count="multiple")
                        upload_btn = gr.Button("上传并解析", variant="primary")
                    with gr.Column(scale=2):
                        report = gr.HTML("<div class='muted'>导入后在此显示质量体检报告</div>")
                gr.Markdown("### 数据集")
                datasets = gr.Dataframe(interactive=False, wrap=True)

            with gr.Tab("🏭 供应商 360"):
                with gr.Row():
                    vendor_dd = gr.Dropdown(label="供应商", choices=supplier360.vendor_options())
                    material_dd = gr.Dropdown(
                        label="物料（跨厂寻源）", choices=supplier360.material_options()
                    )
                profile = gr.HTML("<div class='muted'>选择供应商后显示画像</div>")
                with gr.Row():
                    overview = gr.Dataframe(label="供应概况", interactive=False)
                    rr = gr.Dataframe(label="财务风险（RapidRatings）", interactive=False)
                with gr.Row():
                    price_pos = gr.Dataframe(label="价格定位", interactive=False)
                    po_perf = gr.Dataframe(label="履约表现（代理指标）", interactive=False)
                gr.HTML(
                    "<div class='muted'>注：交付完整性/价格漂移/闭环率为代理指标；真实 OTIF 需补 "
                    "PO 创建日期与承诺交期字段（PRD DQ-05/06）。</div>"
                )
                cross = gr.Dataframe(label="跨厂寻源对比（同物料全工厂）", interactive=False, wrap=True)

            with gr.Tab("🔗 品类整合 FTG"):
                scan_btn = gr.Button("扫描整合机会", variant="primary")
                kpi = gr.HTML("<div class='muted'>点击扫描后显示 FTG 三级漏斗</div>")
                opp = gr.Dataframe(label="整合机会（按支出段，点击行查看明细）", interactive=False)
                with gr.Row():
                    seg_detail = gr.Dataframe(label="机会明细", interactive=False)
                    cbcs_df = gr.Dataframe(label="跨国供料能力 CBCS", interactive=False, wrap=True)

            with gr.Tab("📈 市场监测"):
                with gr.Row():
                    refresh_btn = gr.Button("立即刷新行情", variant="primary")
                    commodity_dd = gr.Dropdown(label="商品", choices=market.commodity_options())
                market_note = gr.HTML("")
                alert_html = gr.HTML("<div class='muted'>刷新后显示异动预警</div>")
                market_df = gr.Dataframe(label="大宗商品行情", interactive=False)
                gr.HTML(
                    "<div class='muted'>主源 TradingEconomics（公开页面、无需登录），"
                    "逐行给出日/周/月/年初至今/同比涨跌与数据日期；抓取失败自动切换"
                    "世界银行 Pink Sheet 兜底（月度口径，1960 年至今，用于历史趋势与分位）。"
                    "所有数字都带来源与时间，不混用不同口径。</div>"
                )
                trend = gr.Plot(label="历史趋势")
                trend_stat = gr.HTML("<div class='muted'>选择商品后显示趋势与分位</div>")

            with gr.Tab("💬 AI 助手"):
                if llm.enabled():
                    gr.ChatInterface(
                        fn=lambda msg, hist: llm.chat(msg, hist),
                        title="采购顾问",
                        description="回答基于数据库当前内容，不编造数字；切换供应商建议需人工审批。",
                    )
                else:
                    gr.HTML(
                        "<div class='card'>未配置 <b>SILICONFLOW_API_KEY</b>，AI 助手未启用。"
                        "在 .env 中填写后重启即可使用。</div>"
                    )

        upload_btn.click(
            do_upload,
            inputs=[files],
            outputs=[report, datasets, vendor_dd, material_dd],
        )
        demo.load(_on_load, outputs=[datasets, vendor_dd, material_dd])
        vendor_dd.change(
            on_vendor, inputs=[vendor_dd], outputs=[profile, overview, price_pos, po_perf, rr]
        )
        material_dd.change(on_material, inputs=[material_dd], outputs=[cross])
        scan_btn.click(on_scan, outputs=[kpi, opp])
        opp.select(on_segment_select, inputs=[opp], outputs=[seg_detail, cbcs_df])
        refresh_btn.click(
            on_market_refresh, outputs=[market_df, alert_html, commodity_dd, market_note]
        )
        commodity_dd.change(on_commodity, inputs=[commodity_dd], outputs=[trend, trend_stat])
    return demo
