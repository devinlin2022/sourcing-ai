# Sourcing AI

面向消费品供应链的**自动寻源助手**：上传 SAP 导出数据，自动完成供应商 360 画像、跨国品类整合（FTG）机会识别、大宗物料行情监测，并给出可追溯的谈判依据。

前端 Gradio + Flowbite 风格，后端 FastAPI，数据库 DuckDB 单文件，公网通过 ngrok 暴露，**默认开启账号密码登录**。

---

## 三个功能

### 1. 供应商 360（Supplier 360）
- 供应商画像：覆盖工厂数 / 国家数 / 物料数 / 覆盖年支出
- 价格定位：标准单价（USD/单位）vs 最优厂单价，溢价百分比
- 履约表现：行项目数、累计收货量、订单金额、交付完整性、价格漂移、订单闭环率、首末收货日
- 财务风险：RapidRatings FHR 分档（0-19 极高 / 20-39 高 / 40-59 中 / 60-79 低 / 80-100 极低），**无评级显示"无评级"，不当作低分**
- **跨厂寻源**：同一物料在所有工厂的报价横向对比，并给出结论（同供应商跨厂价差 ≤5% 视为已趋同；>5% 可作谈判锚点；MOQ 超目标厂年用量 30% 判为不可行）

### 2. 品类整合 FTG（Vendor Consolidation）
- 按支出段扫描整合机会，输出**三级漏斗**：识别（毛差额）→ 验证（扣运费/关税/资金占用/切换成本）→ 实现（人工回填实际进合同的节省）
- 跨国供料能力评分 **CBCS（0-105）**：地理足迹 30 + 出口经验 30 + 商务能力 25 + 合规风险 20
- **每个得分都绑定证据**，缺证据记 0 分且降低置信度；置信度 = 得分/105
- 规则约束：缺 FHR 的供应商**最高只能到 B 级**"需询价确认"，不允许直接判 A 级试点

### 3. 市场监测（Market Watch）
- 大宗商品看板：最新价、日/周/月环比、年初至今、同比，**逐行标注来源与数据日期**
- 主源 **TradingEconomics**（公开页面，无需账号密码，每次刷新抓取）
- 兜底 **World Bank Pink Sheet**（月度，1960 年至今，用于历史趋势与分位）
- 异动预警：月环比绝对值 > 5% 自动高亮
- 每日定时刷新（`MARKET_REFRESH_HOUR`，默认 8 点）

---

## 支持的输入文件

上传即自动识别类型，无需手动指定。重复文件按内容哈希自动跳过；增量文件按主键 UPSERT。

| 文件 | 作用 |
|---|---|
| `Cost Exhibit.csv` | 成本基线：物料 × 工厂 × 供应商 年度成本快照 |
| `PO_HiSTORICAL_Procurement.csv` | PO 采购历史：真实成交价与收货记录（支持增量快照叠加） |
| `ICP System Result.csv` | 工厂 × 物料 × 12 个月标准成本，用于判断涨价是市场行为还是供应商行为 |
| `Vendor Master.csv` / `MATERIAL_INFO_RECORD.csv` | 采购买方主数据，MOQ 与交期约束 |
| `Logistic RateCard.csv` | 起运港 × 目的港 × 船司 × 箱型费率，含市场均价 |
| `Spend Changes Statement.csv` | 支出变动归因 |
| `RapidRatings Vendor Outreach List 2024.xlsx` | 供应商联系人 + FHR 财务风险分 |

---

## 快速开始（本地）

```bash
git clone https://github.com/devinlin2022/sourcing-ai.git
cd sourcing-ai
pip install -r requirements.txt
cp .env.example .env          # 修改 ADMIN_PASSWORD
python run.py --port 7860     # 打开 http://127.0.0.1:7860
```

带公网隧道：

```bash
# .env 里填 NGROK_AUTHTOKEN=你的token（https://dashboard.ngrok.com/get-started/your-authtoken）
python run.py --port 7860 --ngrok
```

登录：默认 `admin / admin123`（**请在 `.env` 里改掉**）。

批量导入已有数据文件（放在仓库上一级目录时）：

```bash
python scripts/seed.py /path/to/your/data
```

---

## 在 Google Colab 上运行

### 方式一：一键打开笔记本

仓库根目录的 `colab.ipynb` 可以直接上传到 Colab（`文件 → 上传笔记本`），按顺序执行即可。核心步骤：

```python
# 1. 拉代码
!git clone https://github.com/devinlin2022/sourcing-ai.git
%cd sourcing-ai

# 2. 装依赖（约 1-2 分钟）
!pip install -q -r requirements.txt

# 3. 配置（密码 + ngrok token）
import os
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASSWORD"] = "改成你自己的密码"
os.environ["NGROK_AUTHTOKEN"] = "你的ngrok token"

# 4. 启动，输出公网地址
from tools.colab import boot
boot()
```

启动后会打印：

```
==================================================
  Sourcing AI 已启动: https://xxxx.ngrok-free.app
  登录: admin / ******
==================================================
```

### 方式二：数据库持久化到 Google Drive

Colab 每次重启会清空磁盘。想让上传的数据留存，先挂载 Drive 并指定 `DB_PATH`：

```python
from google.colab import drive
drive.mount("/content/drive")
import os
os.environ["DB_PATH"] = "/content/drive/MyDrive/sourcing_ai/sourcing.duckdb"
from tools.colab import boot
boot()
```

### Colab 注意事项

- **ngrok token 是必须的**：Colab 无法直接对外暴露端口，没有 token 只能在笔记本内用 `http://127.0.0.1:7860`（浏览器打不开）。
- **免费版 Colab 会休眠**：无人操作约 90 分钟后实例回收，公网链接失效，重新执行 `boot()` 会生成新链接。
- **大文件上传**：100MB+ 的 CSV 建议先传到 Drive，再用 `!cp` 复制到 `/content`，比浏览器上传稳定。
- **私有仓库**：`git clone` 需要 Personal Access Token，用 `https://<user>:<token>@github.com/...` 形式。

---

## 数据口径：三个必须知道的坑

这三个坑都会让金额算错，代码里已做硬性处理，也有回归测试守着。

1. **价格列是「每 1000 单位」报价，用量列是基本单位**
   `STD_PRICE_PER_UNIT_USD × ANNUALIZED_QTY_STD_UOM ÷ 1000 = ANNUALIZED_STD_MTL_SPEND_USD`，28 行比值全部等于 1.000。
   所有「价差 × 用量」必须除以 `PRICE_UNIT_DIVISOR`（默认 1000），否则节省额精确放大 1000 倍。

2. **工厂级字段在供应商行上重复**
   同一 (物料, 工厂) 会出现多条记录（多供应商行 + 主值/微量值）。直接 `SUM(annual_spend)` = 27,850,612 USD，按 (物料, 工厂) 取 `MAX` = **3,986,079 USD**，虚高 **6.99 倍**。
   系统内所有汇总都先归约到 (物料, 工厂) 粒度。

3. **PO 表同一凭证有多行收货记录**
   `(PO, 行项目, 物料凭证)` 会重复出现（一张 PO 分多次 GR），这是真实形态不是脏数据。PO 导入采用**整行去重**，履约指标按 PO 行项目聚合后再计算。

另外：订单价/标准价超出 `[0.5, 2]` 的行会被识别为口径异常 —— **只把可疑的价格字段置空，整行保留**（金额与用量仍然有效，不能因为一个价格字段丢掉 200 万美元支出），审计记录写入 `quarantine` 表，在「数据管理」页可查。

---

## 性能

实测（本机，106.7 MB / 313,600 行 PO 明细）：

| 操作 | 耗时 |
|---|---|
| CSV 解析 + 类型转换 + 入库 | **2.65 s** |
| `count(*)` | 0.001 s |
| 按供应商 `GROUP BY` + `SUM` | 0.005 s |
| 多维度聚合 | 0.007 s |

加速手段：DuckDB 原生列式 CSV 读取（`read_csv` 直接建临时表，不经过 pandas）、全程 SQL 内完成类型转换与异常标记、只对需要改写的字段做 `UPDATE`、内容哈希做重复导入拦截。千万行级数据同理，内存占用与文件大小基本无关。

---

## 项目结构

```
sourcing-ai/
├── app/
│   ├── api.py              # FastAPI + Gradio 挂载 + 定时任务 + 鉴权
│   ├── config.py           # 环境变量、价格除数、FTG 预留比例
│   ├── db.py               # DuckDB 连接与建表
│   ├── ingest/
│   │   ├── profiles.py     # 8 类文件的表头签名与字段映射
│   │   ├── pipeline.py     # CSV 解析、异常标记、UPSERT、质量体检
│   │   ├── reader.py       # 编码探测（UTF-8/GBK）
│   │   └── xlsx.py         # RapidRatings 多 Sheet 解析
│   ├── analysis/
│   │   ├── supplier360.py  # 画像、价格定位、履约、跨厂寻源、RR 匹配
│   │   └── consolidation.py# FTG 扫描、三级漏斗、CBCS 评分
│   ├── market/
│   │   ├── sources.py      # TradingEconomics 抓取 + World Bank 兜底
│   │   └── store.py        # 快照落库、预警、历史趋势
│   ├── llm/client.py       # 硅基流动 DeepSeek 对话（可选）
│   └── ui/app.py           # 五个页签的界面
├── tests/                  # pytest，17 个用例
├── tools/colab.py          # Colab 启动封装
├── run.py                  # 本地/ngrok 启动入口
└── colab.ipynb             # Colab 一键笔记本
```

---

## 测试

```bash
pytest -q
```

覆盖：文件类型识别、重复导入拦截、增量 UPSERT 不产生重复行、**6.99 倍去重守卫**、异常价格置空、FHR 分档、跨厂寻源结论、FTG 公式一致性、CBCS 证据绑定、RR 名称匹配不误配。

> 这些用例校验的是**真实数据的口径陷阱**，需要把业务 CSV / xlsx 放在仓库的上一级目录（默认不会进 Git）。
> 找不到样本数据时会整体 skip 而不是报错，方便别人 clone 后先看代码。

---

## 安全说明

- 公网访问默认开启登录：Gradio 会话登录 + `/api/*` HTTP Basic 双层。
- 密码只从环境变量读取，不写入代码库；`.env` 与 `data/` 已在 `.gitignore` 中。
- **不要把真实供应商报价提交到公开仓库**，样本数据仅用于本地验证。

---

## 数据来源

| 数据 | 来源 | 更新频率 |
|---|---|---|
| 大宗商品行情 | [TradingEconomics](https://tradingeconomics.com/commodities) 公开页面 | 每次点击刷新 / 每日定时 |
| 大宗商品历史 | [World Bank Pink Sheet](https://www.worldbank.org/en/research/commodity-markets) | 月度（每月初更新） |
| 供应商财务风险 | 客户提供的 RapidRatings 导出文件 | 随文件上传 |
| 采购与成本 | 客户 SAP 导出 | 随文件上传 |

界面与 API 返回值中，每条行情都带 `source`（来源）与 `data_date`（数据日期）、`fetched_at`（抓取时间），便于核对时点。

---

## 已知限制

- 无 PO 创建日期与承诺交期字段，**真正的 OTIF 算不出来**，当前用「交付完整性 + 价格漂移 + 闭环率」作为代理指标，界面已标注。
- 无质量检验/退货/扣款字段，"质量表现"无法从现有数据得出。
- RapidRatings 168 家名录中仅 43 家有可用 FHR，样本内 5 家核心供应商 0 匹配，需补采评级或建立人工映射表。
- 物料编码存在双体系（`M06526` vs `P1524023`），ICP 与 Cost Exhibit 关联需人工维护映射。
- FTG「验证」层的运费/关税/资金占用为参数化预留（默认扣 25%），待接入真实费率后替换。
