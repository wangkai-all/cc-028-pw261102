"""承运商扫描导入：字段归一化、去重、落库和导入日志。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .db import Repository
from .domain import parse_bj


def _first(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return default


def normalize_record(
    record: dict[str, Any], default_carrier: str | None, imported_at: datetime
) -> dict[str, Any]:
    """把不同承运商的字段命名归一成内部结构。"""
    tracking_no = str(_first(record, "tracking_no", "waybill_no", "tracking", "mail_no", "") or "").strip()
    scan_id = str(_first(record, "scan_id", "scan_no", "event_id", "id", "") or "").strip()
    carrier = str(_first(record, "carrier", "carrier_code", default=default_carrier) or "").strip()
    raw_code = str(_first(record, "status_code", "status", "scan_code", "code", "") or "").strip()
    occurred_raw = _first(record, "occurred_at", "scan_time", "event_time", "time", "occur_time")
    received_raw = _first(record, "received_at", "received_time", "ingest_time", default=occurred_raw)
    location = str(_first(record, "location", "city", "node", default="") or "").strip()
    description = str(
        _first(record, "description", "detail", "remark", "raw_label", default="") or ""
    ).strip()
    display_name = str(_first(record, "display_name", "receiver", "customer", default="") or "").strip()
    origin = str(_first(record, "origin", default="") or "").strip()
    destination = str(_first(record, "destination", default="") or "").strip()

    return {
        "tracking_no": tracking_no,
        "scan_id": scan_id,
        "carrier": carrier,
        "raw_code": raw_code,
        "raw_label": description,
        "occurred_raw": occurred_raw,
        "received_raw": received_raw,
        "location": location,
        "description": description,
        "display_name": display_name,
        "origin": origin,
        "destination": destination,
        "imported_at": imported_at,
    }


def import_scans(
    repo: Repository,
    records: list[dict[str, Any]],
    source: str,
    carrier: str | None = None,
    imported_at: datetime | None = None,
) -> dict[str, Any]:
    """导入一批扫描。

    - scan_id 全局唯一，重复扫描不覆盖已有记录；
    - 接收时间只用于展示数据到达，排序仍使用发生时间；
    - 未知状态也会入库供轨迹和异常展示，但不会推进状态。
    """
    from .domain import now_beijing

    if not records:
        imported_at = imported_at or now_beijing()
    else:
        imported_at = (
            imported_at
            or parse_bj(_first(records[0], "received_at", default=None))
            or now_beijing()
        )
    mappings = repo.mapping_dict()

    normalized: list[dict[str, Any]] = []
    raw_for_error: list[tuple[int, dict[str, Any], str]] = []
    for index, source_record in enumerate(records):
        item = normalize_record(source_record, carrier, imported_at)
        if not item["tracking_no"]:
            raw_for_error.append((index, source_record, "缺少运单号"))
            continue
        if not item["scan_id"]:
            raw_for_error.append((index, source_record, "缺少扫描编号，无法去重"))
            continue
        if not item["carrier"]:
            raw_for_error.append((index, source_record, "缺少承运商"))
            continue
        if not item["raw_code"]:
            raw_for_error.append((index, source_record, "缺少承运商状态代码"))
            continue
        try:
            occurred_at = parse_bj(item["occurred_raw"])
            received_at = parse_bj(item["received_raw"]) or occurred_at
        except (ValueError, TypeError):
            raw_for_error.append((index, source_record, "时间格式无效"))
            continue
        if occurred_at is None:
            raw_for_error.append((index, source_record, "缺少发生时间"))
            continue
        if received_at is None:
            received_at = occurred_at
        item["occurred_at"] = occurred_at
        item["received_at"] = received_at
        mapped_status = mappings.get((item["carrier"], item["raw_code"]))
        item["mapped_status"] = mapped_status
        item["raw_label"] = item["raw_label"] or item["raw_code"]
        normalized.append(item)

    # 批内先去重，以第一次出现的记录为准。
    batch_seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    batch_duplicates: list[dict[str, Any]] = []
    for item in normalized:
        if item["scan_id"] in batch_seen:
            batch_duplicates.append(
                {
                    "scan_id": item["scan_id"],
                    "tracking_no": item["tracking_no"],
                    "reason": "同一批次中扫描编号重复，保留首次出现记录",
                }
            )
            continue
        batch_seen.add(item["scan_id"])
        candidates.append(item)

    existing = repo.existing_scan_ids([item["scan_id"] for item in candidates])
    batch = repo.create_batch(
        source=source,
        carrier=carrier,
        imported_at=imported_at,
        received_count=len(records),
        inserted_count=0,
        duplicate_count=0,
        rejected_count=len(raw_for_error),
    )

    inserted = 0
    duplicates: list[dict[str, Any]] = [*batch_duplicates]
    for item in candidates:
        scan_id = item["scan_id"]
        if scan_id in existing:
            reason = "扫描编号已存在，重复导入已跳过"
            duplicates.append(
                {
                    "scan_id": scan_id,
                    "tracking_no": item["tracking_no"],
                    "reason": reason,
                }
            )
            repo.record_scan_attempt(
                batch, scan_id, item["tracking_no"], "DUPLICATE", reason, imported_at
            )
            continue

        repo.upsert_package(
            tracking_no=item["tracking_no"],
            carrier=item["carrier"],
            display_name=item["display_name"],
            origin=item["origin"],
            destination=item["destination"],
            created_at=imported_at,
        )
        repo.insert_scan(
            scan_id=scan_id,
            tracking_no=item["tracking_no"],
            carrier=item["carrier"],
            raw_code=item["raw_code"],
            raw_label=item["raw_label"],
            occurred_at=item["occurred_at"],
            received_at=item["received_at"],
            imported_at=imported_at,
            import_batch_id=batch,
            location=item["location"],
            description=item["description"],
        )
        repo.record_scan_attempt(
            batch, scan_id, item["tracking_no"], "INSERTED", None, imported_at
        )
        existing.add(scan_id)
        inserted += 1

    for _index, record, reason in raw_for_error:
        repo.record_scan_attempt(
            batch,
            _first(record, "scan_id", "scan_no", "event_id", "id"),
            _first(record, "tracking_no", "waybill_no", "tracking", "mail_no"),
            "REJECTED",
            reason,
            imported_at,
        )

    duplicate_count = len(duplicates)
    repo._execute(
        """
        UPDATE import_batches SET inserted_count = ?, duplicate_count = ?
        WHERE id = ?
        """,
        [inserted, duplicate_count, batch],
    )

    return {
        "batch_id": batch,
        "source": source,
        "carrier": carrier,
        "imported_at": imported_at.replace(tzinfo=None).isoformat(),
        "received_count": len(records),
        "inserted_count": inserted,
        "duplicate_count": duplicate_count,
        "rejected_count": len(raw_for_error),
        "duplicates": duplicates,
        "rejected": [
            {"index": index, "reason": reason}
            for index, _record, reason in raw_for_error
        ],
        "unknown_status_count": sum(1 for item in candidates if not item["mapped_status"]),
    }
