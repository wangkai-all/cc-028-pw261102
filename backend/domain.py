"""轨迹还原、工作时段与告警计算。

所有时间在本模块内以“北京时间（UTC+8）的 naive datetime”表示，数据库也只
保存这种本地墙钟时间。对外输出时统一补上 +08:00，避免服务器时区影响业务判断。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable

BEIJING = timezone(timedelta(hours=8))
WORK_START = time(9, 0)
WORK_END = time(18, 0)
STALL_HOURS = 4.0
OVERALL_TIMEOUT_HOURS = 24.0

STATUS_META: dict[str, dict[str, Any]] = {
    "PENDING": {
        "label": "待揽收",
        "short": "待揽收",
        "rank": 0,
        "terminal": False,
        "description": "尚未收到有效的揽收扫描",
        "tone": "neutral",
    },
    "PICKED_UP": {
        "label": "揽收",
        "short": "已揽收",
        "rank": 10,
        "terminal": False,
        "description": "承运商已完成上门取件",
        "tone": "blue",
    },
    "IN_TRANSIT": {
        "label": "运输",
        "short": "运输中",
        "rank": 20,
        "terminal": False,
        "description": "包裹在干线、分拨中心之间移动",
        "tone": "aqua",
    },
    "ARRIVED": {
        "label": "到站",
        "short": "已到站",
        "rank": 30,
        "terminal": False,
        "description": "包裹到达目的地网点或派送站",
        "tone": "violet",
    },
    "OUT_FOR_DELIVERY": {
        "label": "派送",
        "short": "派送中",
        "rank": 40,
        "terminal": False,
        "description": "快递员已出站，正在派送",
        "tone": "orange",
    },
    "DELIVERED": {
        "label": "签收",
        "short": "已签收",
        "rank": 50,
        "terminal": False,
        "description": "收件人已签收，轨迹完成",
        "tone": "green",
    },
    "RETURNED": {
        "label": "退回",
        "short": "已退回",
        "rank": 60,
        "terminal": True,
        "description": "包裹进入退回流程并结束",
        "tone": "serious",
    },
    "CANCELLED": {
        "label": "取消",
        "short": "已取消",
        "rank": 70,
        "terminal": True,
        "description": "运单已取消，不再继续运输",
        "tone": "critical",
    },
}

PROGRESS_STATUSES = {
    "PICKED_UP": 10,
    "IN_TRANSIT": 20,
    "ARRIVED": 30,
    "OUT_FOR_DELIVERY": 40,
    "DELIVERED": 50,
}

TERMINAL_STATUSES = {"RETURNED", "CANCELLED"}
NON_ALARM_STATUSES = {"DELIVERED", "RETURNED", "CANCELLED"}
ALERT_META = {
    "STALLED": {
        "label": "停滞",
        "description": "连续 4 个工作小时没有有效进展",
        "tone": "warning",
        "icon": "pause",
    },
    "OVERALL_TIMEOUT": {
        "label": "整体超时",
        "description": "揽收至签收超过 24 个工作小时",
        "tone": "critical",
        "icon": "clock",
    },
}


def now_beijing() -> datetime:
    """当前北京时间，去掉 tzinfo（数据库中的墙钟表示）。"""
    return datetime.now(BEIJING).replace(tzinfo=None, microsecond=0)


def parse_bj(value: str | datetime | date | None) -> datetime | None:
    """把任意时间输入规范成北京时间墙钟时间。无时区输入默认按北京时间理解。"""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime.combine(value, time.min)
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError(f"无法解析时间：{value}") from exc
    if dt.tzinfo is None:
        return dt.replace(microsecond=0)
    return dt.astimezone(BEIJING).replace(tzinfo=None, microsecond=0)


def iso_bj(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(BEIJING).replace(tzinfo=None)
    return value.replace(tzinfo=BEIJING).isoformat()


def date_bj(value: datetime | None) -> str | None:
    return value.date().isoformat() if value else None


def format_hours(seconds: float) -> float:
    """秒 -> 小时，保留两位小数。"""
    return round(max(0.0, seconds) / 3600.0, 2)


def format_hours_text(seconds: float) -> str:
    hours = format_hours(seconds)
    if hours == int(hours):
        return f"{int(hours)} 小时"
    return f"{hours:.2f} 小时".replace(".00", "")


def _window_for_day(day: date) -> tuple[datetime, datetime]:
    return datetime.combine(day, WORK_START), datetime.combine(day, WORK_END)


def holiday_map(holidays: Iterable[Any]) -> dict[date, str]:
    """接受 date / ISO 字符串 / 数据集行。"""
    result: dict[date, str] = {}
    for item in holidays:
        if isinstance(item, dict):
            raw_date = item.get("holiday_date") or item.get("date")
            name = item.get("name") or "导入节假日"
        else:
            raw_date = item
            name = "导入节假日"
        if isinstance(raw_date, date):
            d = raw_date
        else:
            d = date.fromisoformat(str(raw_date)[:10])
        result[d] = name
    return result


def workday_info(day: date, holidays: dict[date, str]) -> tuple[bool, str | None]:
    holiday_name = holidays.get(day)
    if holiday_name:
        return False, holiday_name
    if day.weekday() >= 5:
        return False, "周末"
    return True, None


@dataclass
class BusinessClock:
    segments: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    seconds: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "segments": self.segments,
            "skipped": self.skipped,
            "seconds": round(self.seconds, 1),
            "hours": format_hours(self.seconds),
        }


def business_clock(
    start: datetime | None,
    end: datetime | None,
    holidays: Iterable[Any] | dict[date, str],
) -> BusinessClock:
    """计算 [start, end) 内落在北京工作日 09:00-18:00 的时间。

    segments 是实际计入的连续时段，skipped 列出被跳过的周末和导入节假日，
    便于告警详情解释“时间累计在哪里”。
    """
    clock = BusinessClock()
    if start is None or end is None or start >= end:
        return clock
    hmap = holidays if isinstance(holidays, dict) else holiday_map(holidays)
    day = start.date()
    last_day = end.date()
    while day <= last_day:
        window_start, window_end = _window_for_day(day)
        is_workday, skip_reason = workday_info(day, hmap)
        if not is_workday:
            # 只有当天与计算区间有交集时才记录跳过原因。
            if max(start, window_start) < min(end, window_end):
                clock.skipped.append(
                    {
                        "date": day.isoformat(),
                        "reason": skip_reason,
                        "hours_not_counted": format_hours(
                            (min(end, window_end) - max(start, window_start)).total_seconds()
                        ),
                    }
                )
        else:
            seg_start = max(start, window_start)
            seg_end = min(end, window_end)
            if seg_start < seg_end:
                duration = (seg_end - seg_start).total_seconds()
                clock.seconds += duration
                clock.segments.append(
                    {
                        "date": day.isoformat(),
                        "start": iso_bj(seg_start),
                        "end": iso_bj(seg_end),
                        "hours": format_hours(duration),
                    }
                )
        day += timedelta(days=1)
    return clock


def business_seconds(
    start: datetime | None,
    end: datetime | None,
    holidays: Iterable[Any] | dict[date, str],
) -> float:
    return business_clock(start, end, holidays).seconds


def workday_clock_now(now: datetime, holidays: dict[date, str]) -> dict[str, Any]:
    day = now.date()
    workday, skip_reason = workday_info(day, holidays)
    in_window = WORK_START <= now.time() < WORK_END
    return {
        "now": iso_bj(now),
        "weekday": "一二三四五六日"[day.weekday()],
        "is_workday": workday,
        "is_counting": bool(workday and in_window),
        "skip_reason": skip_reason,
        "window": "09:00–18:00",
    }


@dataclass
class TimelineEvent:
    scan_id: str
    tracking_no: str
    carrier: str
    raw_code: str
    raw_label: str
    mapped_status: str | None
    occurred_at: datetime
    received_at: datetime
    imported_at: datetime
    import_batch_id: int | None
    location: str
    description: str
    is_effective: bool = False
    anomaly_code: str | None = None
    anomaly_reason: str | None = None
    late_arrival: bool = False

    def to_dict(self) -> dict[str, Any]:
        meta = STATUS_META.get(self.mapped_status or "PENDING", STATUS_META["PENDING"])
        return {
            "scan_id": self.scan_id,
            "tracking_no": self.tracking_no,
            "carrier": self.carrier,
            "raw_code": self.raw_code,
            "raw_label": self.raw_label,
            "mapped_status": self.mapped_status,
            "mapped_label": meta["label"] if self.mapped_status else "未映射",
            "occurred_at": iso_bj(self.occurred_at),
            "received_at": iso_bj(self.received_at),
            "imported_at": iso_bj(self.imported_at),
            "import_batch_id": self.import_batch_id,
            "location": self.location,
            "description": self.description,
            "is_effective": self.is_effective,
            "anomaly_code": self.anomaly_code,
            "anomaly_reason": self.anomaly_reason,
            "late_arrival": self.late_arrival,
            "received_delay_hours": format_hours(
                (self.received_at - self.occurred_at).total_seconds()
            ),
        }


@dataclass
class Analysis:
    package: dict[str, Any]
    timeline: list[TimelineEvent]
    status: str
    status_at: datetime | None
    last_scan_at: datetime | None
    last_effective_at: datetime | None
    pickup_at: datetime | None
    delivered_at: datetime | None
    returned_at: datetime | None
    cancelled_at: datetime | None
    anomalies: list[dict[str, Any]] = field(default_factory=list)
    late_count: int = 0
    ignored_future_count: int = 0

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def waiting_clock(self, as_of: datetime, holidays: dict[date, str]) -> BusinessClock:
        return business_clock(self.last_effective_at, as_of, holidays)

    def elapsed_clock(self, as_of: datetime, holidays: dict[date, str]) -> BusinessClock | None:
        if not self.pickup_at:
            return None
        end = self.delivered_at if self.status == "DELIVERED" else as_of
        return business_clock(self.pickup_at, end, holidays)

    def overall_clock(
        self, as_of: datetime, holidays: dict[date, str]
    ) -> BusinessClock | None:
        if not self.pickup_at:
            return None
        end = self.delivered_at if self.status == "DELIVERED" else as_of
        if not end or self.status in TERMINAL_STATUSES and self.status != "DELIVERED":
            return None
        return business_clock(self.pickup_at, end, holidays)


def reconstruct(
    package: dict[str, Any],
    raw_events: Iterable[dict[str, Any]],
    mappings: dict[tuple[str, str], str],
    holidays: Iterable[Any] | dict[date, str],
    as_of: datetime,
) -> Analysis:
    """按“发生时间”而不是接收时间还原轨迹。

    - 观察时刻之后发生的扫描完全不参与判断；
    - 线性状态只允许向前推进，重复阶段不刷新“有效进展”；
    - 未知状态、已签收后回退等不推进当前状态，只记为异常；
    - 晚到的早期扫描会被排入它发生时的位置，不会把已签收包裹拉回运输中。
    """
    hmap = holidays if isinstance(holidays, dict) else holiday_map(holidays)
    ordered = sorted(
        raw_events,
        key=lambda e: (
            e["occurred_at"],
            e.get("received_at") or e["occurred_at"],
            str(e.get("scan_id") or ""),
        ),
    )

    timeline: list[TimelineEvent] = []
    anomalies: list[dict[str, Any]] = []
    ignored_future = 0
    current_status: str | None = None
    max_rank = -1
    status_at: datetime | None = None
    last_scan_at: datetime | None = None
    last_effective_at: datetime | None = None
    pickup_at: datetime | None = None
    delivered_at: datetime | None = None
    returned_at: datetime | None = None
    cancelled_at: datetime | None = None

    for row in ordered:
        occurred_at: datetime = row["occurred_at"]
        received_at: datetime = row.get("received_at") or occurred_at
        if occurred_at > as_of:
            ignored_future += 1
            continue

        carrier = row.get("carrier") or package.get("carrier") or ""
        raw_code = str(row.get("raw_code") or "")
        mapped = mappings.get((carrier, raw_code))
        raw_label = row.get("raw_label") or raw_code
        effective = False
        anomaly_code = None
        anomaly_reason = None

        # 接收时间与发生时间相差 4 小时以上，标记为“晚到”；它只影响展示，
        # 不改变排序依据。
        late_arrival = (received_at - occurred_at) >= timedelta(hours=4)

        if not mapped:
            anomaly_code = "UNKNOWN_STATUS"
            anomaly_reason = (
                f"未知状态代码 {raw_code}（{carrier}），不推进当前进度"
            )
        elif mapped in TERMINAL_STATUSES:
            if current_status in TERMINAL_STATUSES:
                if current_status != mapped:
                    anomaly_code = "TERMINAL_CONFLICT"
                    anomaly_reason = (
                        f"包裹已处于{STATUS_META[current_status]['label']}，"
                        f"又收到{mapped == 'RETURNED' and '退回' or '取消'}扫描，不改变当前状态"
                    )
            elif current_status == "DELIVERED" and mapped == "CANCELLED":
                anomaly_code = "REGRESSION"
                anomaly_reason = "已签收包裹出现取消扫描，按异常处理，保持签收状态"
            else:
                effective = True
                current_status = mapped
                status_at = occurred_at
                last_effective_at = occurred_at
                if mapped == "RETURNED":
                    returned_at = occurred_at
                else:
                    cancelled_at = occurred_at
        elif mapped in PROGRESS_STATUSES:
            rank = PROGRESS_STATUSES[mapped]
            if current_status in TERMINAL_STATUSES:
                anomaly_code = "TERMINAL_REGRESSION"
                anomaly_reason = (
                    f"包裹已{STATUS_META[current_status]['label']}，"
                    f"又出现{STATUS_META[mapped]['label']}扫描，不推进进度"
                )
            elif rank > max_rank:
                effective = True
                max_rank = rank
                current_status = mapped
                status_at = occurred_at
                last_effective_at = occurred_at
                if mapped == "PICKED_UP" and pickup_at is None:
                    pickup_at = occurred_at
                if mapped == "DELIVERED":
                    delivered_at = occurred_at
            elif rank == max_rank:
                # 同一阶段的重复扫描是正常物流节点，但不构成“有效进展”，
                # 因此不会重置停滞计时。
                pass
            else:
                prev_label = STATUS_META.get(current_status or "PENDING", STATUS_META["PENDING"])[
                    "label"
                ]
                anomaly_code = "REGRESSION"
                anomaly_reason = (
                    f"状态从{prev_label}回退到{STATUS_META[mapped]['label']}，"
                    "不推进当前进度"
                )
                if current_status == "DELIVERED":
                    anomaly_reason = (
                        "包裹已签收，晚到扫描显示运输节点；保持签收状态，不回退进度"
                    )

        if anomaly_code:
            anomalies.append(
                {
                    "scan_id": row.get("scan_id"),
                    "occurred_at": iso_bj(occurred_at),
                    "code": anomaly_code,
                    "reason": anomaly_reason,
                }
            )

        event = TimelineEvent(
            scan_id=row.get("scan_id") or "",
            tracking_no=row.get("tracking_no") or package["tracking_no"],
            carrier=carrier,
            raw_code=raw_code,
            raw_label=raw_label,
            mapped_status=mapped,
            occurred_at=occurred_at,
            received_at=received_at,
            imported_at=row.get("imported_at") or received_at,
            import_batch_id=row.get("import_batch_id"),
            location=row.get("location") or "",
            description=row.get("description") or raw_label,
            is_effective=effective,
            anomaly_code=anomaly_code,
            anomaly_reason=anomaly_reason,
            late_arrival=late_arrival,
        )
        timeline.append(event)
        last_scan_at = occurred_at

    if current_status is None:
        current_status = "PENDING"

    late_count = sum(1 for event in timeline if event.late_arrival)
    return Analysis(
        package=package,
        timeline=timeline,
        status=current_status,
        status_at=status_at,
        last_scan_at=last_scan_at,
        last_effective_at=last_effective_at,
        pickup_at=pickup_at,
        delivered_at=delivered_at,
        returned_at=returned_at,
        cancelled_at=cancelled_at,
        anomalies=anomalies,
        late_count=late_count,
        ignored_future_count=ignored_future,
    )


def compute_alerts(
    analysis: Analysis,
    as_of: datetime,
    holidays: Iterable[Any] | dict[date, str],
) -> list[dict[str, Any]]:
    """计算当前观察时刻的活跃告警，同一包裹同一类型至多一条。"""
    hmap = holidays if isinstance(holidays, dict) else holiday_map(holidays)
    alerts: list[dict[str, Any]] = []
    status = analysis.status
    if status in TERMINAL_STATUSES:
        return alerts

    # 停滞：从最近一次有效进展到现在。重复节点、异常扫描都不重置计时。
    if status != "DELIVERED" and analysis.last_effective_at is not None:
        clock = business_clock(analysis.last_effective_at, as_of, hmap)
        if clock.seconds >= STALL_HOURS * 3600:
            last_label = STATUS_META.get(status, STATUS_META["PENDING"])["label"]
            alerts.append(
                {
                    "type": "STALLED",
                    "label": ALERT_META["STALLED"]["label"],
                    "reason": (
                        f"已连续 {format_hours_text(clock.seconds)} 无有效进展，"
                        f"当前停在「{last_label}」"
                    ),
                    "hours": format_hours(clock.seconds),
                    "threshold_hours": STALL_HOURS,
                    "start": iso_bj(analysis.last_effective_at),
                    "end": iso_bj(as_of),
                    "last_effective_status": last_label,
                    "segments": clock.segments,
                    "skipped": clock.skipped,
                    "business_seconds": round(clock.seconds, 1),
                    "package_status": status,
                }
            )

    # 整体超时：揽收 ->（已签收则签收时间，否则观察时刻）超过 24 工作小时。
    if analysis.pickup_at is not None:
        end = analysis.delivered_at if status == "DELIVERED" else as_of
        if end is not None and end >= analysis.pickup_at:
            clock = business_clock(analysis.pickup_at, end, hmap)
            if clock.seconds > OVERALL_TIMEOUT_HOURS * 3600:
                if status == "DELIVERED":
                    reason = (
                        f"揽收至签收累计 {format_hours_text(clock.seconds)}，"
                        "超过 24 个工作小时"
                    )
                    signed_note = "已签收"
                else:
                    reason = (
                        f"揽收后已累计 {format_hours_text(clock.seconds)}，"
                        "仍未签收，超过 24 个工作小时"
                    )
                    signed_note = "尚未签收"
                alerts.append(
                    {
                        "type": "OVERALL_TIMEOUT",
                        "label": ALERT_META["OVERALL_TIMEOUT"]["label"],
                        "reason": reason,
                        "hours": format_hours(clock.seconds),
                        "threshold_hours": OVERALL_TIMEOUT_HOURS,
                        "start": iso_bj(analysis.pickup_at),
                        "end": iso_bj(end),
                        "delivery_state": signed_note,
                        "segments": clock.segments,
                        "skipped": clock.skipped,
                        "business_seconds": round(clock.seconds, 1),
                        "package_status": status,
                    }
                )
    return alerts


def sort_key_package(summary: dict[str, Any]) -> tuple:
    """告警优先、停滞时长降序、最近扫描降序。"""
    active = summary.get("active_alert_count", 0)
    waiting = summary.get("waiting_business_hours") or 0
    last_scan = summary.get("last_scan_at") or ""
    return (-active, -waiting, last_scan)


def summarize(
    analysis: Analysis,
    as_of: datetime,
    holidays: Iterable[Any] | dict[date, str],
    active_alerts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    hmap = holidays if isinstance(holidays, dict) else holiday_map(holidays)
    alerts = active_alerts if active_alerts is not None else compute_alerts(analysis, as_of, hmap)
    meta = STATUS_META.get(analysis.status, STATUS_META["PENDING"])
    waiting_clock = analysis.waiting_clock(as_of, hmap)
    overall_clock = analysis.overall_clock(as_of, hmap)
    completed = analysis.status in {"DELIVERED", "RETURNED", "CANCELLED"}
    pkg = analysis.package
    return {
        "tracking_no": pkg["tracking_no"],
        "carrier": pkg["carrier"],
        "carrier_name": pkg.get("carrier_name") or pkg["carrier"],
        "display_name": pkg.get("display_name") or "",
        "origin": pkg.get("origin") or "",
        "destination": pkg.get("destination") or "",
        "status": analysis.status,
        "status_label": meta["label"],
        "status_description": meta["description"],
        "status_at": iso_bj(analysis.status_at),
        "last_scan_at": iso_bj(analysis.last_scan_at),
        "last_effective_at": iso_bj(analysis.last_effective_at),
        "pickup_at": iso_bj(analysis.pickup_at),
        "delivered_at": iso_bj(analysis.delivered_at),
        "returned_at": iso_bj(analysis.returned_at),
        "cancelled_at": iso_bj(analysis.cancelled_at),
        "is_terminal": analysis.is_terminal,
        "is_completed": completed,
        "is_open": not completed,
        "waiting_business_hours": (
            format_hours(waiting_clock.seconds) if not completed else None
        ),
        "overall_business_hours": (
            format_hours(overall_clock.seconds) if overall_clock is not None else None
        ),
        "anomaly_count": len(analysis.anomalies),
        "late_scan_count": analysis.late_count,
        "events_count": len(analysis.timeline),
        "active_alert_count": len(alerts),
        "alerts": alerts,
        "active_alert_types": [alert["type"] for alert in alerts],
        "ignored_future_count": analysis.ignored_future_count,
    }


def analysis_to_detail(
    analysis: Analysis,
    summary: dict[str, Any],
    as_of: datetime,
    holidays: Iterable[Any] | dict[date, str],
) -> dict[str, Any]:
    hmap = holidays if isinstance(holidays, dict) else holiday_map(holidays)
    timeline = [event.to_dict() for event in analysis.timeline]
    return {
        "package": {
            **analysis.package,
            "carrier_name": analysis.package.get("carrier_name") or analysis.package["carrier"],
        },
        "as_of": iso_bj(as_of),
        "summary": summary,
        "timeline": timeline,
        "anomalies": analysis.anomalies,
        "alerts": summary["alerts"],
        "business_clock": {
            "pickup_at": iso_bj(analysis.pickup_at),
            "last_effective_at": iso_bj(analysis.last_effective_at),
            "last_effective_status": (
                STATUS_META.get(analysis.status, {}).get("label")
                if analysis.last_effective_at
                else None
            ),
            "waiting": analysis.waiting_clock(as_of, hmap).as_dict(),
            "overall": (
                analysis.overall_clock(as_of, hmap).as_dict()
                if analysis.overall_clock(as_of, hmap) is not None
                else None
            ),
        },
        "ignored_future_count": analysis.ignored_future_count,
    }
