from dataclasses import dataclass, field


@dataclass
class Col:
    src: str
    dst: str
    typ: str = "VARCHAR"
    zero_null: bool = False


@dataclass
class Profile:
    pid: str
    table: str
    label: str
    signatures: list
    cols: list
    keys: list
    anomaly: str | None = None
    anomaly_note: str = "数据异常，已隔离"
    anomaly_null: list = field(default_factory=list)
    upsert: str = "keys"


V, D, I, DT = "VARCHAR", "DOUBLE", "INTEGER", "DATE"

_COST_ANOMALY = (
    "order_price IS NOT NULL AND std_price IS NOT NULL "
    "AND (order_price < 0.5 * std_price OR order_price > 2 * std_price)"
)

PROFILES = [
    Profile(
        pid="cost_exhibit",
        table="cost_exhibit",
        label="Cost Exhibit 成本基线",
        signatures=["std_price_per_unit_usd", "leader_plant"],
        keys=["material", "plant", "vendor_name"],
        anomaly=_COST_ANOMALY,
        anomaly_note="订单价/标准价比值超出 [0.5,2]，疑似单位口径不一致",
        anomaly_null=["order_price"],
        cols=[
            Col("MATERIAL", "material"),
            Col("PLANT", "plant"),
            Col("PLANT_COUNTRY", "plant_country"),
            Col("PLANT_CITY", "plant_city"),
            Col("CATEGORY", "category"),
            Col("SUBCATEGORY", "subcategory"),
            Col("SPEND_SEGMENT", "spend_segment"),
            Col("SPEND_SUB_SEGMENT", "spend_sub_segment"),
            Col("VENDOR_NUM", "vendor_num"),
            Col("VENDOR_NAME", "vendor_name"),
            Col("COUNTRY_OF_ORIGIN", "country_of_origin"),
            Col("INCOTERMS", "incoterms"),
            Col("MOQ", "moq", D),
            Col("STD_PRICE_PER_UNIT_USD", "std_price", D, True),
            Col("ORDER_PRICE_PER_UNIT_USD", "order_price", D, True),
            Col("ANNUALIZED_QTY_STD_UOM", "annual_qty", D),
            Col("ANNUALIZED_STD_MTL_SPEND_USD", "annual_spend", D),
            Col("LEADER_PLANT", "leader_plant"),
            Col("LEADER_STD_PRICE_USD", "leader_price", D),
            Col("SUPPLIER_COUNT", "supplier_count", I),
            Col("COO_COUNT", "coo_count", I),
            Col("FTG_OPPORTUNITY_MM_USD", "ftg_mm", D),
            Col("VALIDITY_DATE", "validity_date"),
            Col("PROCUREMENT_TYPE", "procurement_type"),
        ],
    ),
    Profile(
        pid="po_history",
        table="po_history",
        label="PO 采购历史",
        signatures=["po line order qty", "material document"],
        keys=["po_num", "line_item", "material_doc"],
        upsert="row",
        cols=[
            Col("Client", "client"),
            Col("Plant", "plant"),
            Col("Purchase Order", "po_num"),
            Col("Line Item", "line_item"),
            Col("Material Document", "material_doc"),
            Col("Material", "material"),
            Col("Material Description", "material_desc"),
            Col("Vendor ID", "vendor_id"),
            Col("Vendor Name", "vendor_name"),
            Col("PO Line Order Qty", "order_qty", D),
            Col("PO Base Unit", "base_unit"),
            Col("PO Net Price", "net_price", D),
            Col("PO Price Unit", "price_unit", D),
            Col("PO Effective Unit Price", "eff_unit_price", D),
            Col("PO Net Value", "net_value", D),
            Col("PO Header Currency", "currency"),
            Col("SubSegment", "subsegment"),
            Col("Year", "year", I),
            Col("Posting Date", "posting_date", DT),
            Col("History Qty", "history_qty", D),
            Col("Amount in LC", "amount_lc", D),
            Col("IR Per Unit LC", "ir_unit_lc", D),
            Col("IR Per Unit FC", "ir_unit_fc", D),
            Col("Incoterms", "incoterms"),
            Col("Completed Delivery", "completed"),
        ],
    ),
    Profile(
        pid="icp",
        table="icp_result",
        label="ICP 标准成本",
        signatures=["icp_measure"],
        keys=["period", "target_org", "material", "measure"],
        cols=[
            Col("Period", "period"),
            Col("CURRENCY", "currency"),
            Col("Target Organization", "target_org"),
            Col("MATERIAL", "material"),
            Col("Material Description", "material_desc"),
            Col("ICP_MEASURE", "measure"),
            Col("ICP_VALUE", "value", D),
            Col("STANDARD_PRICE", "std_price", D),
            Col("PLANT_COUNTRY", "plant_country"),
            Col("SEGMENT", "segment"),
            Col("SUB_SPEND_SEGMENT", "sub_segment"),
        ],
    ),
    Profile(
        pid="vendor_master",
        table="vendor_master",
        label="Vendor Master 供应商主数据",
        signatures=["lead_time_from_mrp"],
        keys=["plant", "material", "vendor_id"],
        cols=[
            Col("PLANT__WERKS", "plant"),
            Col("COUNTRY_KEY__LAND1", "country"),
            Col("MATERIAL__MATNR", "material"),
            Col("VENDOR_ID__LIFNR", "vendor_id"),
            Col("VENDOR_NAME__NAME1", "vendor_name"),
            Col("LEAD_TIME_FROM_MRP__PLIFZ", "lead_time", I),
            Col("MOQ_FROM_MRP__BSTMI", "moq", D),
            Col("INFO_RECORD_NET_PRICE__NETPR", "net_price", D),
            Col("COP__WAERS", "currency"),
        ],
    ),
    Profile(
        pid="info_record",
        table="info_record",
        label="采购信息记录",
        signatures=["info_record_number_eina"],
        keys=["info_rec_num", "plant"],
        cols=[
            Col("INFO_RECORD_NUMBER_EINA", "info_rec_num"),
            Col("VENDOR", "vendor_id"),
            Col("VENDOR_NAME", "vendor_name"),
            Col("MATERIAL", "material"),
            Col("PURCHASING_ORGANIZATION", "purch_org"),
            Col("PLANT", "plant"),
            Col("ORDER_UNIT", "order_unit"),
            Col("PLANNED_DELIV_TIME", "lead_time", I),
            Col("MINIMUM_ORDER_QUANTITY", "moq", D),
            Col("OVERDELIVERY_TOLERANCE", "over_tol", D),
            Col("NET_PRICE", "net_price", D),
            Col("CURRENCY_KEY", "currency"),
            Col("INCOTERMS", "incoterms"),
        ],
    ),
    Profile(
        pid="logistics_rate",
        table="logistics_rate",
        label="物流费率卡",
        signatures=["your rate"],
        keys=["origin_code", "dest_code", "carrier", "container_type"],
        cols=[
            Col("Origin Name", "origin_name"),
            Col("Origin Code", "origin_code"),
            Col("Destination Name", "dest_name"),
            Col("Destination Code", "dest_code"),
            Col("Supplier", "carrier"),
            Col("Container Type", "container_type"),
            Col("Valid From", "valid_from", DT),
            Col("Valid To", "valid_to", DT),
            Col("Your Rate", "your_rate", D),
            Col("Market Average", "market_avg", D),
            Col("Market Low", "market_low", D),
            Col("Market High", "market_high", D),
        ],
    ),
    Profile(
        pid="spend_changes",
        table="spend_changes",
        label="花费变动表",
        signatures=["icp measure"],
        keys=["period", "division", "target_org", "measure"],
        cols=[
            Col("Period", "period"),
            Col("Division Description", "division"),
            Col("Target Organization", "target_org"),
            Col("Icp Measure", "measure"),
            Col("USD Value", "value_raw"),
        ],
    ),
]


def detect_profile(headers: list[str]) -> Profile | None:
    lowered = [h.strip().lower() for h in headers]
    for p in PROFILES:
        if all(any(sig in h for h in lowered) for sig in p.signatures):
            return p
    return None
