"""FastAPI 应用：轨迹、告警、状态映射和导入接口。"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .db import get_repository
from .domain import (
    ALERT_META,
    BEIJING,
    OVERALL_TIMEOUT_HOURS,
    STALL_HOURS,
    STATUS_META,
    iso_bj,
    now_beijing,
    parse_bj,
    sort_key_package,
    workday_clock_now,
)
from .importer import import_scans
from .seed import HOLIDAYS, MAPPINGS, CARRIERS, seed_database, supplement_sample

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = os.environ.get("TRACKER_DB_PATH", str(ROOT / "data" / "tracking.duckdb"))
FRONTEND_DIST = ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    repo = get_repository(DB_PATH)
    if not repo.packages_raw():
        seed_database(repo)
    app.state.repo = repo
    yield


app = FastAPI(
    title="轨迹哨站 API",
    description="包裹轨迹还原、工作时段告警与承运商扫描映射",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def repo():
    return app.state.repo


def resolve_as_of(value: str | None) -> Any:
    if not value:
        return now_beijing()
    try:
        parsed = parse_bj(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if parsed is None:
        raise HTTPException(status_code=400, detail="观察时刻不能为空")
    return parsed


class ImportRequest(BaseModel):
    source: str = Field(default="手动导入")
    carrier: str | None = None
    imported_at: str | None = None
    records: list[dict[str, Any]]
    recalculate: bool = True


class HolidayImportRequest(BaseModel):
    dates: list[str]
    name: str = "导入节假日"
    recalculate: bool = True


class RecalculateRequest(BaseModel):
    as_of: str | None = None


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "now": iso_bj(now_beijing()), "timezone": "Asia/Shanghai (UTC+8)"}


@app.get("/api/overview")
def overview(as_of: str | None = Query(default=None)) -> dict[str, Any]:
    observed = resolve_as_of(as_of)
    summaries, _analyses = repo().analyze_all(observed)
    holidays = repo().holiday_dict()

    status_counts: dict[str, int] = {code: 0 for code in STATUS_META}
    for summary in summaries:
        status_counts[summary["status"]] = status_counts.get(summary["status"], 0) + 1

    active_alerts: list[dict[str, Any]] = []
    for summary in summaries:
        for alert in summary["alerts"]:
            active_alerts.append(
                {
                    **alert,
                    "id": f"{summary['tracking_no']}:{alert['type']}",
                    "tracking_no": summary["tracking_no"],
                    "carrier": summary["carrier"],
                    "carrier_name": summary["carrier_name"],
                    "display_name": summary["display_name"],
                    "origin": summary["origin"],
                    "destination": summary["destination"],
                    "package_status": summary["status"],
                    "package_status_label": summary["status_label"],
                }
            )
    active_alerts.sort(
        key=lambda alert: (
            0 if alert["type"] == "OVERALL_TIMEOUT" else 1,
            -float(alert.get("hours") or 0),
            alert["tracking_no"],
        )
    )

    carriers: dict[str, int] = {}
    for summary in summaries:
        carriers[summary["carrier"]] = carriers.get(summary["carrier"], 0) + 1

    open_statuses = {"PICKED_UP", "IN_TRANSIT", "ARRIVED", "OUT_FOR_DELIVERY"}
    alert_types = [alert["type"] for alert in active_alerts]
    return {
        "as_of": iso_bj(observed),
        "now": iso_bj(now_beijing()),
        "timezone": "北京时间（UTC+8）",
        "work_clock": workday_clock_now(observed, holidays),
        "thresholds": {
            "stall_hours": STALL_HOURS,
            "overall_timeout_hours": OVERALL_TIMEOUT_HOURS,
            "work_window": "09:00–18:00",
        },
        "totals": {
            "packages": len(summaries),
            "open": sum(1 for summary in summaries if summary["status"] in open_statuses),
            "delivered": status_counts.get("DELIVERED", 0),
            "returned": status_counts.get("RETURNED", 0),
            "cancelled": status_counts.get("CANCELLED", 0),
            "pending": status_counts.get("PENDING", 0),
            "stalled": alert_types.count("STALLED"),
            "overdue": alert_types.count("OVERALL_TIMEOUT"),
            "active_alerts": len(active_alerts),
            "anomalies": sum(summary["anomaly_count"] for summary in summaries),
            "late_scans": sum(summary["late_scan_count"] for summary in summaries),
        },
        "status_counts": status_counts,
        "carrier_counts": carriers,
        "active_alerts": active_alerts,
        "status_catalog": [
            {"code": code, **meta} for code, meta in STATUS_META.items()
        ],
        "alert_catalog": [
            {"type": key, **meta} for key, meta in ALERT_META.items()
        ],
        "holidays": repo().holidays(),
    }


@app.get("/api/packages")
def packages(
    as_of: str | None = Query(default=None),
    q: str | None = Query(default=None),
    carrier: str | None = Query(default=None),
    status: str | None = Query(default=None),
    alert_only: bool = Query(default=False),
    alert_type: str | None = Query(default=None),
) -> dict[str, Any]:
    observed = resolve_as_of(as_of)
    summaries, _analyses = repo().analyze_all(observed)
    query = (q or "").strip().lower()
    if query:
        summaries = [
            summary
            for summary in summaries
            if query
            in " ".join(
                [
                    summary["tracking_no"],
                    summary["display_name"],
                    summary["origin"],
                    summary["destination"],
                    summary["carrier_name"],
                ]
            ).lower()
        ]
    if carrier:
        summaries = [summary for summary in summaries if summary["carrier"] == carrier]
    if status:
        summaries = [summary for summary in summaries if summary["status"] == status]
    if alert_only:
        summaries = [summary for summary in summaries if summary["active_alert_count"] > 0]
    if alert_type:
        summaries = [
            summary
            for summary in summaries
            if alert_type in summary["active_alert_types"]
        ]
    summaries.sort(key=sort_key_package)
    return {
        "as_of": iso_bj(observed),
        "total": len(summaries),
        "items": summaries,
    }


@app.get("/api/packages/{tracking_no}")
def package_detail(tracking_no: str, as_of: str | None = Query(default=None)) -> dict[str, Any]:
    observed = resolve_as_of(as_of)
    detail = repo().package_detail(tracking_no, observed)
    if not detail:
        raise HTTPException(status_code=404, detail="未找到该包裹")
    return detail


@app.get("/api/packages/{tracking_no}/alert-history")
def package_alert_history(tracking_no: str) -> dict[str, Any]:
    if not repo().package_raw(tracking_no):
        raise HTTPException(status_code=404, detail="未找到该包裹")
    return {
        "tracking_no": tracking_no,
        "items": repo().alert_history(tracking_no),
        "current": [
            row
            for row in repo().current_alerts()
            if row["tracking_no"] == tracking_no
        ],
    }


@app.get("/api/alerts")
def alerts(as_of: str | None = Query(default=None)) -> dict[str, Any]:
    observed = resolve_as_of(as_of)
    summaries, _analyses = repo().analyze_all(observed)
    items = []
    for summary in summaries:
        for alert in summary["alerts"]:
            items.append(
                {
                    **alert,
                    "id": f"{summary['tracking_no']}:{alert['type']}",
                    "tracking_no": summary["tracking_no"],
                    "carrier": summary["carrier"],
                    "carrier_name": summary["carrier_name"],
                    "display_name": summary["display_name"],
                    "origin": summary["origin"],
                    "destination": summary["destination"],
                    "package_status": summary["status"],
                    "package_status_label": summary["status_label"],
                    "last_effective_at": summary["last_effective_at"],
                }
            )
    items.sort(
        key=lambda alert: (
            0 if alert["type"] == "OVERALL_TIMEOUT" else 1,
            -float(alert.get("hours") or 0),
            alert["tracking_no"],
        )
    )
    return {"as_of": iso_bj(observed), "total": len(items), "items": items}


@app.get("/api/alerts/history")
def alert_history(tracking_no: str | None = Query(default=None)) -> dict[str, Any]:
    return {"items": repo().alert_history(tracking_no)}


@app.get("/api/mappings")
def mappings() -> dict[str, Any]:
    carriers = repo().carrier_map()
    rows = repo()._rows(
        """
        SELECT carrier, raw_code, raw_label, canonical_status
        FROM status_mappings ORDER BY carrier, raw_code
        """
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["carrier"], []).append(
            {
                "raw_code": row["raw_code"],
                "raw_label": row["raw_label"],
                "canonical_status": row["canonical_status"],
                "canonical_label": STATUS_META.get(row["canonical_status"], {}).get(
                    "label", row["canonical_status"]
                ),
            }
        )
    carrier_list = [
        {
            "code": code,
            "name": name,
            "mappings": grouped.get(code, []),
        }
        for code, name in sorted(
            carriers.items(),
            key=lambda item: next(
                (order for carrier_code, carrier_name, order in CARRIERS if carrier_code == item[0]),
                99,
            ),
        )
    ]

    known = {(row["carrier"], row["raw_code"]) for row in rows}
    all_codes = repo()._rows(
        "SELECT DISTINCT carrier, raw_code, raw_label FROM scan_events"
    )
    unmapped = [
        {
            "carrier": row["carrier"],
            "raw_code": row["raw_code"],
            "raw_label": row["raw_label"],
            "canonical_status": None,
            "canonical_label": "未映射",
        }
        for row in all_codes
        if (row["carrier"], row["raw_code"]) not in known
    ]
    return {
        "carriers": carrier_list,
        "canonical": [{"code": code, **meta} for code, meta in STATUS_META.items()],
        "alert_catalog": [{"type": key, **meta} for key, meta in ALERT_META.items()],
        "unmapped": unmapped,
        "thresholds": {
            "stall_hours": STALL_HOURS,
            "overall_timeout_hours": OVERALL_TIMEOUT_HOURS,
        },
    }


@app.get("/api/holidays")
def holidays() -> dict[str, Any]:
    return {"items": repo().holidays(), "seed": [{"date": d, "name": n} for d, n in HOLIDAYS]}


@app.get("/api/imports")
def imports(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    return {"items": repo().import_batches(limit)}


@app.get("/api/imports/{batch_id}")
def import_detail(batch_id: int) -> dict[str, Any]:
    item = repo().batch_detail(batch_id)
    if not item:
        raise HTTPException(status_code=404, detail="未找到导入批次")
    return item


@app.post("/api/scans/import")
def scans_import(payload: ImportRequest) -> dict[str, Any]:
    batch_imported_at = parse_bj(payload.imported_at) if payload.imported_at else now_beijing()
    result = import_scans(
        repo(),
        payload.records,
        source=payload.source,
        carrier=payload.carrier,
        imported_at=batch_imported_at,
    )
    recalc = repo().recalculate() if payload.recalculate else None
    return {"import": result, "recalculated": recalc}


@app.post("/api/holidays/import")
def holidays_import(payload: HolidayImportRequest) -> dict[str, Any]:
    inserted = repo().import_holidays(payload.dates, payload.name)
    recalc = repo().recalculate() if payload.recalculate else None
    return {
        "inserted": inserted,
        "holidays": repo().holidays(),
        "recalculated": recalc,
    }


@app.post("/api/recalculate")
def recalculate(payload: RecalculateRequest | None = None) -> dict[str, Any]:
    observed = resolve_as_of(payload.as_of if payload else None)
    return repo().recalculate(as_of=observed)


@app.get("/api/demo/supplement")
def demo_supplement(tracking_no: str | None = Query(default=None)) -> dict[str, Any] | None:
    # 没有可补录的停滞件是正常业务状态，返回 null 而不是让弹窗报 404。
    return supplement_sample(repo(), tracking_no)


@app.post("/api/packages/{tracking_no}/supplement")
def supplement_package(tracking_no: str) -> dict[str, Any]:
    sample = supplement_sample(repo(), tracking_no)
    if not sample:
        raise HTTPException(status_code=404, detail="当前没有可补录的停滞包裹")
    result = import_scans(
        repo(),
        [sample["record"]],
        source="补录缺失扫描",
        carrier=sample["carrier"],
        imported_at=now_beijing(),
    )
    recalc = repo().recalculate()
    return {"import": result, "recalculated": recalc, "sample": sample}


@app.post("/api/demo/reset")
def demo_reset() -> dict[str, Any]:
    seeded = seed_database(repo(), reset=True)
    return {"ok": True, "seeded": seeded}


@app.get("/api/config")
def config() -> dict[str, Any]:
    return {
        "timezone": "Asia/Shanghai",
        "timezone_label": "北京时间",
        "business_hours": "09:00–18:00",
        "stall_hours": STALL_HOURS,
        "overall_timeout_hours": OVERALL_TIMEOUT_HOURS,
        "statuses": [{"code": code, **meta} for code, meta in STATUS_META.items()],
        "alerts": [{"type": key, **meta} for key, meta in ALERT_META.items()],
        "carrier_map": repo().carrier_map(),
        "mappings": {carrier: list(rules.keys()) for carrier, rules in MAPPINGS.items()},
    }


# ---- 静态前端（构建后由 FastAPI 直接提供） ----
if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
