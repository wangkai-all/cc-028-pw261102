"""演示数据：跨周末、国庆长假、晚到扫描、重复导入、异常与补录场景。"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from .db import Repository
from .domain import iso_bj, now_beijing
from .importer import import_scans

CARRIERS = [
    ("SF", "顺丰速运", 1),
    ("ZTO", "中通快递", 2),
    ("YTO", "圆通速递", 3),
    ("JD", "京东物流", 4),
]

# 承运商代码 -> (中文标签, 规范状态)
MAPPINGS: dict[str, dict[str, tuple[str, str]]] = {
    "SF": {
        "SF_PICKUP": ("上门揽收", "PICKED_UP"),
        "SF_TRANSIT": ("干线运输", "IN_TRANSIT"),
        "SF_HUB": ("到达分拨中心", "ARRIVED"),
        "SF_DELIVERING": ("快递员派送", "OUT_FOR_DELIVERY"),
        "SF_SIGNED": ("收件人签收", "DELIVERED"),
        "SF_RETURN": ("退回流转", "RETURNED"),
        "SF_CANCEL": ("运单取消", "CANCELLED"),
    },
    "ZTO": {
        "PICKUP": ("已揽收", "PICKED_UP"),
        "TRANSPORT": ("运输中", "IN_TRANSIT"),
        "ARRIVE": ("到达网点", "ARRIVED"),
        "DISPATCH": ("网点派送", "OUT_FOR_DELIVERY"),
        "SIGN": ("已签收", "DELIVERED"),
        "RETURN": ("退回", "RETURNED"),
        "CANCEL": ("取消", "CANCELLED"),
    },
    "YTO": {
        "YTO_ACCEPT": ("收件扫描", "PICKED_UP"),
        "YTO_TRANSIT": ("中转运输", "IN_TRANSIT"),
        "YTO_ARRIVE": ("到达目的地", "ARRIVED"),
        "YTO_DELIVER": ("开始派送", "OUT_FOR_DELIVERY"),
        "YTO_SIGN": ("签收成功", "DELIVERED"),
        "YTO_RETURN": ("退回件", "RETURNED"),
        "YTO_CANCEL": ("订单取消", "CANCELLED"),
    },
    "JD": {
        "JD_COLLECT": ("京东揽收", "PICKED_UP"),
        "JD_TRANSFER": ("分拣转运", "IN_TRANSIT"),
        "JD_ARRIVE": ("到达站点", "ARRIVED"),
        "JD_DISPATCH": ("配送员出发", "OUT_FOR_DELIVERY"),
        "JD_SIGN": ("妥投签收", "DELIVERED"),
        "JD_RETURN": ("退货入库", "RETURNED"),
        "JD_CANCEL": ("订单取消", "CANCELLED"),
    },
}

HOLIDAYS = [
    ("2026-10-01", "国庆长假"),
    ("2026-10-02", "国庆长假"),
    ("2026-10-03", "国庆长假"),
    ("2026-10-04", "国庆长假"),
    ("2026-10-05", "国庆长假"),
    ("2026-10-06", "国庆长假"),
    ("2026-10-07", "国庆长假"),
]


def _at(now: datetime, days_ago: int, hour: int, minute: int = 0) -> datetime:
    return (now - timedelta(days=days_ago)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )


def _last_friday(now: datetime) -> date:
    today = now.date()
    diff = (today.weekday() - 4) % 7
    if diff == 0:
        diff = 7
    return today - timedelta(days=diff)


def _event(
    tracking_no: str,
    carrier: str,
    code: str,
    scan_id: str,
    occurred: datetime,
    received: datetime,
    location: str,
    description: str | None = None,
) -> dict[str, Any]:
    label = MAPPINGS.get(carrier, {}).get(code, (code, None))[0]
    return {
        "tracking_no": tracking_no,
        "carrier": carrier,
        "scan_id": scan_id,
        "status_code": code,
        "occurred_at": iso_bj(occurred),
        "received_at": iso_bj(received),
        "location": location,
        "description": description or f"{location} · {label}",
    }


def seed_database(repo: Repository, reset: bool = False) -> dict[str, Any]:
    if reset:
        repo.wipe_all()

    now = now_beijing()
    today = now.date()

    for code, name, order in CARRIERS:
        repo.add_carrier(code, name, order)
    for carrier, rules in MAPPINGS.items():
        for raw_code, (raw_label, canonical) in rules.items():
            repo.add_mapping(carrier, raw_code, raw_label, canonical)
    repo.import_holidays([item[0] for item in HOLIDAYS], "国庆长假")

    # 1) 普通跨周末件：周五晚揽收，周一上午签收。
    friday = _last_friday(now)
    saturday = friday + timedelta(days=1)
    sunday = friday + timedelta(days=2)
    monday = friday + timedelta(days=3)
    repo.upsert_package(
        "SF-DEMO-1001",
        "SF",
        "林晓 · 相框",
        "杭州",
        "上海",
        _at(now, (today - friday).days, 16, 20),
    )
    sf_cross_weekend = [
        _event(
            "SF-DEMO-1001", "SF", "SF_PICKUP", "SF1001-001",
            datetime.combine(friday, time(16, 30)), datetime.combine(friday, time(16, 36)),
            "杭州西湖营业点",
        ),
        _event(
            "SF-DEMO-1001", "SF", "SF_TRANSIT", "SF1001-002",
            datetime.combine(friday, time(17, 20)), datetime.combine(friday, time(17, 24)),
            "杭州转运中心",
        ),
        _event(
            "SF-DEMO-1001", "SF", "SF_HUB", "SF1001-003",
            datetime.combine(monday, time(9, 30)), datetime.combine(monday, time(9, 35)),
            "上海虹桥分拨中心",
        ),
        _event(
            "SF-DEMO-1001", "SF", "SF_DELIVERING", "SF1001-004",
            datetime.combine(monday, time(10, 0)), datetime.combine(monday, time(10, 4)),
            "上海长宁派送站",
        ),
        _event(
            "SF-DEMO-1001", "SF", "SF_SIGNED", "SF1001-005",
            datetime.combine(monday, time(10, 25)), datetime.combine(monday, time(10, 28)),
            "上海长宁 · 前台代收",
        ),
    ]

    # 2) 国庆长假件：付款后在长假期间停在运输段，节后到站签收。用于展示节假日跳过。
    repo.upsert_package(
        "ZTO-DEMO-2002", "ZTO", "周宁 · 茶叶礼盒", "广州", "北京",
        datetime(2026, 9, 30, 15, 40),
    )
    zto_holiday = [
        _event(
            "ZTO-DEMO-2002", "ZTO", "PICKUP", "ZTO2002-001",
            datetime(2026, 9, 30, 16, 0), datetime(2026, 9, 30, 16, 7),
            "广州荔湾揽收点",
        ),
        _event(
            "ZTO-DEMO-2002", "ZTO", "TRANSPORT", "ZTO2002-002",
            datetime(2026, 9, 30, 17, 0), datetime(2026, 9, 30, 17, 9),
            "广州白云分拨中心",
        ),
        _event(
            "ZTO-DEMO-2002", "ZTO", "ARRIVE", "ZTO2002-003",
            datetime(2026, 10, 8, 16, 30), datetime(2026, 10, 8, 16, 38),
            "北京朝阳网点",
        ),
        _event(
            "ZTO-DEMO-2002", "ZTO", "DISPATCH", "ZTO2002-004",
            datetime(2026, 10, 8, 17, 0), datetime(2026, 10, 8, 17, 3),
            "北京朝阳派送站",
        ),
        _event(
            "ZTO-DEMO-2002", "ZTO", "SIGN", "ZTO2002-005",
            datetime(2026, 10, 8, 17, 18), datetime(2026, 10, 8, 17, 21),
            "北京朝阳 · 本人签收",
        ),
    ]

    # 3) 当前停滞件；缺失一条“到站”扫描，支持演示补录后重算。
    repo.upsert_package(
        "YTO-DEMO-3003", "YTO", "陈越 · 显示器支架", "成都", "深圳",
        _at(now, 4, 9, 0),
    )
    yto_stalled = [
        _event(
            "YTO-DEMO-3003", "YTO", "YTO_ACCEPT", "YTO3003-001",
            _at(now, 4, 9, 10), _at(now, 4, 9, 16),
            "成都武侯揽收点",
        ),
        _event(
            "YTO-DEMO-3003", "YTO", "YTO_TRANSIT", "YTO3003-002",
            _at(now, 4, 10, 30), _at(now, 4, 10, 38),
            "成都双流分拨中心",
        ),
    ]

    # 4) 整体超时件：跨周末，揽收到签收超过 24 个工作小时。
    repo.upsert_package(
        "JD-DEMO-4004", "JD", "顾言 · 办公椅", "苏州", "武汉",
        _at(now, 8, 8, 40),
    )
    jd_timeout = [
        _event(
            "JD-DEMO-4004", "JD", "JD_COLLECT", "JD4004-001",
            _at(now, 8, 9, 0), _at(now, 8, 9, 6),
            "苏州工业园揽收站",
        ),
        _event(
            "JD-DEMO-4004", "JD", "JD_TRANSFER", "JD4004-002",
            _at(now, 7, 9, 0), _at(now, 7, 9, 12),
            "苏州分拣中心",
        ),
        _event(
            "JD-DEMO-4004", "JD", "JD_ARRIVE", "JD4004-003",
            _at(now, 6, 9, 0), _at(now, 6, 9, 4),
            "武汉东西湖站",
        ),
        _event(
            "JD-DEMO-4004", "JD", "JD_DISPATCH", "JD4004-004",
            _at(now, 2, 15, 30), _at(now, 2, 15, 34),
            "武汉江汉配送站",
        ),
        _event(
            "JD-DEMO-4004", "JD", "JD_SIGN", "JD4004-005",
            _at(now, 2, 17, 0), _at(now, 2, 17, 2),
            "武汉江汉 · 前台签收",
        ),
    ]

    # 5) 晚到扫描 + 重复导入 + 签收后回退异常。
    repo.upsert_package(
        "SF-DEMO-5005", "SF", "许安 · 书籍", "南京", "合肥",
        _at(now, 6, 8, 50),
    )
    sf_late = [
        _event(
            "SF-DEMO-5005", "SF", "SF_PICKUP", "SF5005-001",
            _at(now, 6, 9, 0), _at(now, 6, 9, 4),
            "南京鼓楼营业点",
        ),
        _event(
            "SF-DEMO-5005", "SF", "SF_TRANSIT", "SF5005-002",
            _at(now, 6, 10, 0), _at(now, 6, 10, 3),
            "南京江宁转运中心",
        ),
        _event(
            "SF-DEMO-5005", "SF", "SF_HUB", "SF5005-003",
            _at(now, 6, 14, 0), _at(now, 6, 14, 3),
            "合肥包河分拨中心",
        ),
        _event(
            "SF-DEMO-5005", "SF", "SF_DELIVERING", "SF5005-004",
            _at(now, 5, 9, 10), _at(now, 5, 9, 14),
            "合肥蜀山派送站",
        ),
        _event(
            "SF-DEMO-5005", "SF", "SF_SIGNED", "SF5005-005",
            _at(now, 5, 10, 20), _at(now, 5, 10, 22),
            "合肥蜀山 · 本人签收",
        ),
    ]
    sf_late_delayed = [
        _event(
            "SF-DEMO-5005", "SF", "SF_HUB", "SF5005-LATE-ARRIVE",
            _at(now, 6, 13, 0), _at(now, 1, 17, 0),
            "合肥包河分拨中心（补录）",
            "晚到补录：发生时间早于已签收，插入历史轨迹",
        ),
        _event(
            "SF-DEMO-5005", "SF", "SF_TRANSIT", "SF5005-LATE-REGRESS",
            _at(now, 5, 14, 0), _at(now, 1, 17, 5),
            "合肥蜀山派送站（异常回传）",
            "已签收后回传的运输扫描，应列异常但不回退状态",
        ),
    ]

    # 6) 未知状态代码件。
    repo.upsert_package(
        "SF-DEMO-8008", "SF", "沈知 · 进口咖啡豆", "宁波", "杭州",
        _at(now, 2, 10, 30),
    )
    sf_unknown = [
        _event(
            "SF-DEMO-8008", "SF", "SF_PICKUP", "SF8008-001",
            _at(now, 2, 11, 0), _at(now, 2, 11, 5),
            "宁波鄞州营业点",
        ),
        _event(
            "SF-DEMO-8008", "SF", "SF_TRANSIT", "SF8008-002",
            _at(now, 1, 16, 0), _at(now, 1, 16, 5),
            "宁波北仑转运中心",
        ),
        _event(
            "SF-DEMO-8008", "SF", "SF_CUSTOMS_HOLD", "SF8008-003",
            _at(now, 1, 17, 0), _at(now, 1, 17, 5),
            "杭州海关查验区",
            "海关查验中，承运商代码未在字典中",
        ),
    ]

    # 7) 退回与取消件，单独统计。
    repo.upsert_package(
        "ZTO-DEMO-6006", "ZTO", "白露 · 鞋", "泉州", "上海",
        _at(now, 7, 8, 50),
    )
    zto_returned = [
        _event(
            "ZTO-DEMO-6006", "ZTO", "PICKUP", "ZTO6006-001",
            _at(now, 7, 9, 0), _at(now, 7, 9, 5),
            "泉州丰泽揽收点",
        ),
        _event(
            "ZTO-DEMO-6006", "ZTO", "DISPATCH", "ZTO6006-002",
            _at(now, 4, 10, 0), _at(now, 4, 10, 5),
            "上海浦东派送站",
        ),
        _event(
            "ZTO-DEMO-6006", "ZTO", "RETURN", "ZTO6006-003",
            _at(now, 2, 15, 0), _at(now, 2, 15, 6),
            "上海浦东 · 拒收退回",
        ),
    ]
    repo.upsert_package(
        "YTO-DEMO-7007", "YTO", "苏禾 · 花瓶", "佛山", "长沙",
        _at(now, 5, 9, 20),
    )
    yto_cancelled = [
        _event(
            "YTO-DEMO-7007", "YTO", "YTO_ACCEPT", "YTO7007-001",
            _at(now, 5, 9, 30), _at(now, 5, 9, 35),
            "佛山南海揽收点",
        ),
        _event(
            "YTO-DEMO-7007", "YTO", "YTO_CANCEL", "YTO7007-002",
            _at(now, 5, 10, 30), _at(now, 5, 10, 31),
            "佛山南海揽收点",
            "客户取消寄件",
        ),
    ]

    batches: list[dict[str, Any]] = []
    batches.append(
        import_scans(
            repo,
            sf_cross_weekend + sf_late + sf_unknown,
            "顺丰 · 首批扫描",
            "SF",
            imported_at=_at(now, 1, 18, 0),
        )
    )
    batches.append(
        import_scans(
            repo,
            zto_holiday + zto_returned,
            "中通 · 首批扫描",
            "ZTO",
            imported_at=datetime(2026, 10, 8, 18, 10),
        )
    )
    batches.append(
        import_scans(
            repo,
            yto_stalled + yto_cancelled,
            "圆通 · 首批扫描",
            "YTO",
            imported_at=_at(now, 1, 18, 10),
        )
    )
    batches.append(
        import_scans(
            repo,
            jd_timeout,
            "京东 · 首批扫描",
            "JD",
            imported_at=_at(now, 1, 18, 15),
        )
    )
    batches.append(
        import_scans(
            repo,
            sf_late_delayed,
            "顺丰 · 晚到补传批次",
            "SF",
            imported_at=_at(now, 1, 17, 30),
        )
    )
    batches.append(
        import_scans(
            repo,
            sf_cross_weekend + sf_late,
            "顺丰 · 重复导入演练",
            "SF",
            imported_at=_at(now, 1, 18, 20),
        )
    )

    # 长假的告警历史：节后 15:00 仍在停滞，17:18 签收后解除。
    checkpoint_active = datetime(2026, 10, 8, 15, 0)
    checkpoint_delivered = datetime(2026, 10, 8, 17, 30)
    repo.recalculate(
        as_of=checkpoint_active,
        only_tracking_no="ZTO-DEMO-2002",
        history_at=checkpoint_active,
    )
    repo.recalculate(
        as_of=checkpoint_delivered,
        only_tracking_no="ZTO-DEMO-2002",
        history_at=checkpoint_delivered,
    )
    # 当前时刻重算，其他演示告警落成当前状态。
    current = repo.recalculate(as_of=now)

    packages = repo.packages_raw()
    return {
        "packages": len(packages),
        "batches": batches,
        "recalculated": current,
        "now": iso_bj(now),
    }


def supplement_sample(repo: Repository, tracking_no: str | None = None) -> dict[str, Any] | None:
    """为停滞件生成一条可补录的“到站”扫描，用于演示补录后重算。"""
    from .domain import compute_alerts

    now = now_beijing()
    holidays = repo.holiday_dict()
    mappings = repo.mapping_dict()
    packages = repo.packages_raw()
    target = None
    if tracking_no:
        target = next((p for p in packages if p["tracking_no"] == tracking_no), None)
    else:
        stalled_candidates: list[tuple[Any, Any, Any]] = []
        for pkg in packages:
            analysis = repo.analyze_package(pkg, now, mappings, holidays)
            alerts = compute_alerts(analysis, now, holidays)
            if any(alert["type"] == "STALLED" for alert in alerts):
                stalled_candidates.append((analysis.last_effective_at, pkg, analysis))
        # 优先补录停滞最久的包裹，避免因为包裹表排序而随机选到较轻的异常件。
        stalled_candidates.sort(key=lambda item: item[0] or now)
        target = stalled_candidates[0][1] if stalled_candidates else None
    if not target:
        return None

    arrived_code = next(
        (
            raw_code
            for (carrier, raw_code), canonical in mappings.items()
            if carrier == target["carrier"] and canonical == "ARRIVED"
        ),
        None,
    )
    if not arrived_code:
        return None

    occurred = now - timedelta(minutes=45)
    record = {
        "tracking_no": target["tracking_no"],
        "carrier": target["carrier"],
        "scan_id": f"SUPPLEMENT-{target['tracking_no']}-{now.strftime('%Y%m%d%H%M%S')}",
        "status_code": arrived_code,
        "occurred_at": iso_bj(occurred),
        "received_at": iso_bj(now),
        "location": f"{target.get('destination') or '目的地'}网点",
        "description": "补录：到达目的地站点（演示数据）",
    }
    return {
        "tracking_no": target["tracking_no"],
        "carrier": target["carrier"],
        "record": record,
        "explanation": (
            "这条扫描发生在 45 分钟前，但此前未到达系统。补入后按发生时间排在轨迹中，"
            "并会重新计算停滞告警。"
        ),
    }
