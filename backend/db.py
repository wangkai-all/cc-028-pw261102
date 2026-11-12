"""DuckDB 数据访问层。单连接加锁，适合单进程 FastAPI 服务。"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import duckdb

from .domain import Analysis, compute_alerts, iso_bj, now_beijing, reconstruct, summarize

SCHEMA = """
CREATE TABLE IF NOT EXISTS carriers (
    code VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS packages (
    tracking_no VARCHAR PRIMARY KEY,
    carrier VARCHAR NOT NULL,
    display_name VARCHAR,
    origin VARCHAR,
    destination VARCHAR,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS status_mappings (
    carrier VARCHAR NOT NULL,
    raw_code VARCHAR NOT NULL,
    raw_label VARCHAR,
    canonical_status VARCHAR NOT NULL,
    PRIMARY KEY (carrier, raw_code)
);

CREATE TABLE IF NOT EXISTS holidays (
    holiday_date DATE PRIMARY KEY,
    name VARCHAR NOT NULL,
    imported_at TIMESTAMP NOT NULL
);

CREATE SEQUENCE IF NOT EXISTS import_batch_seq START 1;
CREATE SEQUENCE IF NOT EXISTS scan_attempt_seq START 1;

CREATE TABLE IF NOT EXISTS import_batches (
    id BIGINT PRIMARY KEY,
    source VARCHAR NOT NULL,
    carrier VARCHAR,
    imported_at TIMESTAMP NOT NULL,
    received_count INTEGER NOT NULL DEFAULT 0,
    inserted_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    rejected_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scan_events (
    scan_id VARCHAR PRIMARY KEY,
    tracking_no VARCHAR NOT NULL,
    carrier VARCHAR NOT NULL,
    raw_code VARCHAR NOT NULL,
    raw_label VARCHAR,
    occurred_at TIMESTAMP NOT NULL,
    received_at TIMESTAMP NOT NULL,
    imported_at TIMESTAMP NOT NULL,
    import_batch_id BIGINT,
    location VARCHAR,
    description VARCHAR
);

CREATE TABLE IF NOT EXISTS scan_attempts (
    id BIGINT PRIMARY KEY,
    batch_id BIGINT,
    scan_id VARCHAR,
    tracking_no VARCHAR,
    outcome VARCHAR NOT NULL,
    reason VARCHAR,
    attempted_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_current (
    tracking_no VARCHAR NOT NULL,
    alert_type VARCHAR NOT NULL,
    state VARCHAR NOT NULL,
    reason VARCHAR,
    details_json VARCHAR,
    first_seen_at TIMESTAMP,
    last_changed_at TIMESTAMP,
    last_evaluated_at TIMESTAMP,
    resolved_at TIMESTAMP,
    PRIMARY KEY (tracking_no, alert_type)
);

CREATE SEQUENCE IF NOT EXISTS alert_history_seq START 1;
CREATE TABLE IF NOT EXISTS alert_history (
    id BIGINT PRIMARY KEY,
    tracking_no VARCHAR NOT NULL,
    alert_type VARCHAR NOT NULL,
    change_type VARCHAR NOT NULL,
    from_state VARCHAR,
    to_state VARCHAR NOT NULL,
    reason VARCHAR,
    details_json VARCHAR,
    changed_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_tracking ON scan_events(tracking_no);
CREATE INDEX IF NOT EXISTS idx_attempts_tracking ON scan_attempts(tracking_no);
"""


class Repository:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(self.db_path)
        self.lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self.lock:
            self.conn.execute(SCHEMA)

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    def _rows(self, sql: str, params: Iterable[Any] | None = None) -> list[dict[str, Any]]:
        with self.lock:
            result = self.conn.execute(sql, list(params) if params else None)
            description = result.description
            if not description:
                return []
            names = [item[0] for item in description]
            return [dict(zip(names, row)) for row in result.fetchall()]

    def _execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        with self.lock:
            return self.conn.execute(sql, list(params) if params else None)

    def _next_seq(self, sequence: str) -> int:
        result = self._execute(f"SELECT nextval('{sequence}')").fetchone()
        return int(result[0])

    def wipe_all(self) -> None:
        """清空业务表，供演示环境重置。保留 schema 与序列。"""
        for table in (
            "scan_attempts",
            "scan_events",
            "alert_history",
            "alert_current",
            "import_batches",
            "holidays",
            "status_mappings",
            "packages",
            "carriers",
        ):
            self._execute(f"DELETE FROM {table}")

    # ---------- metadata ----------

    def carrier_map(self) -> dict[str, str]:
        return {
            row["code"]: row["name"]
            for row in self._rows("SELECT code, name FROM carriers")
        }

    def mapping_dict(self) -> dict[tuple[str, str], str]:
        return {
            (row["carrier"], row["raw_code"]): row["canonical_status"]
            for row in self._rows("SELECT carrier, raw_code, canonical_status FROM status_mappings")
        }

    def holidays(self) -> list[dict[str, Any]]:
        rows = self._rows(
            "SELECT holiday_date, name, imported_at FROM holidays ORDER BY holiday_date"
        )
        return [
            {
                "date": row["holiday_date"].isoformat(),
                "name": row["name"],
                "imported_at": iso_bj(row["imported_at"]),
            }
            for row in rows
        ]

    def holiday_dict(self) -> dict:
        return {row["holiday_date"]: row["name"] for row in self._rows(
            "SELECT holiday_date, name FROM holidays"
        )}

    def packages_raw(self) -> list[dict[str, Any]]:
        carriers = self.carrier_map()
        rows = self._rows(
            """
            SELECT tracking_no, carrier, display_name, origin, destination, created_at
            FROM packages ORDER BY tracking_no
            """
        )
        for row in rows:
            row["carrier_name"] = carriers.get(row["carrier"], row["carrier"])
        return rows

    def package_raw(self, tracking_no: str) -> dict[str, Any] | None:
        rows = self._rows(
            """
            SELECT tracking_no, carrier, display_name, origin, destination, created_at
            FROM packages WHERE tracking_no = ?
            """,
            [tracking_no],
        )
        if not rows:
            return None
        row = rows[0]
        row["carrier_name"] = self.carrier_map().get(row["carrier"], row["carrier"])
        return row

    # ---------- write paths ----------

    def upsert_package(
        self,
        tracking_no: str,
        carrier: str,
        display_name: str = "",
        origin: str = "",
        destination: str = "",
        created_at: datetime | None = None,
    ) -> None:
        created_at = created_at or now_beijing()
        self._execute(
            """
            INSERT INTO packages (tracking_no, carrier, display_name, origin, destination, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (tracking_no) DO UPDATE SET
                carrier = excluded.carrier,
                display_name = CASE WHEN packages.display_name = '' OR packages.display_name IS NULL
                    THEN excluded.display_name ELSE packages.display_name END,
                origin = CASE WHEN packages.origin = '' OR packages.origin IS NULL
                    THEN excluded.origin ELSE packages.origin END,
                destination = CASE WHEN packages.destination = '' OR packages.destination IS NULL
                    THEN excluded.destination ELSE packages.destination END
            """,
            [tracking_no, carrier, display_name, origin, destination, created_at],
        )

    def add_carrier(self, code: str, name: str, sort_order: int = 0) -> None:
        self._execute(
            """
            INSERT INTO carriers (code, name, sort_order) VALUES (?, ?, ?)
            ON CONFLICT (code) DO UPDATE SET name = excluded.name,
                sort_order = excluded.sort_order
            """,
            [code, name, sort_order],
        )

    def add_mapping(
        self, carrier: str, raw_code: str, raw_label: str, canonical_status: str
    ) -> None:
        self._execute(
            """
            INSERT INTO status_mappings (carrier, raw_code, raw_label, canonical_status)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (carrier, raw_code) DO UPDATE SET
                raw_label = excluded.raw_label,
                canonical_status = excluded.canonical_status
            """,
            [carrier, raw_code, raw_label, canonical_status],
        )

    def import_holidays(self, dates: list[str], name: str) -> int:
        imported_at = now_beijing()
        inserted = 0
        for raw in dates:
            d = raw[:10]
            try:
                from datetime import date as date_cls

                value = date_cls.fromisoformat(d)
            except ValueError:
                continue
            self._execute(
                """
                INSERT INTO holidays (holiday_date, name, imported_at) VALUES (?, ?, ?)
                ON CONFLICT (holiday_date) DO UPDATE SET name = excluded.name,
                    imported_at = excluded.imported_at
                """,
                [value, name, imported_at],
            )
            inserted += 1
        return inserted

    def create_batch(
        self,
        source: str,
        carrier: str | None,
        imported_at: datetime,
        received_count: int,
        inserted_count: int,
        duplicate_count: int,
        rejected_count: int,
    ) -> int:
        batch_id = self._next_seq("import_batch_seq")
        self._execute(
            """
            INSERT INTO import_batches
            (id, source, carrier, imported_at, received_count, inserted_count,
             duplicate_count, rejected_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                batch_id,
                source,
                carrier,
                imported_at,
                received_count,
                inserted_count,
                duplicate_count,
                rejected_count,
            ],
        )
        return batch_id

    def record_scan_attempt(
        self,
        batch_id: int,
        scan_id: str | None,
        tracking_no: str | None,
        outcome: str,
        reason: str | None,
        attempted_at: datetime,
    ) -> None:
        self._execute(
            """
            INSERT INTO scan_attempts
            (id, batch_id, scan_id, tracking_no, outcome, reason, attempted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                self._next_seq("scan_attempt_seq"),
                batch_id,
                scan_id,
                tracking_no,
                outcome,
                reason,
                attempted_at,
            ],
        )

    def existing_scan_ids(self, scan_ids: list[str]) -> set[str]:
        if not scan_ids:
            return set()
        result: set[str] = set()
        # DuckDB 单条 IN 查询足够；分块以避开极长 SQL。
        for start in range(0, len(scan_ids), 500):
            chunk = scan_ids[start : start + 500]
            placeholders = ",".join(["?"] * len(chunk))
            rows = self._rows(
                f"SELECT scan_id FROM scan_events WHERE scan_id IN ({placeholders})", chunk
            )
            result.update(row["scan_id"] for row in rows)
        return result

    def insert_scan(
        self,
        scan_id: str,
        tracking_no: str,
        carrier: str,
        raw_code: str,
        raw_label: str,
        occurred_at: datetime,
        received_at: datetime,
        imported_at: datetime,
        import_batch_id: int,
        location: str,
        description: str,
    ) -> None:
        self._execute(
            """
            INSERT INTO scan_events
            (scan_id, tracking_no, carrier, raw_code, raw_label, occurred_at,
             received_at, imported_at, import_batch_id, location, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                scan_id,
                tracking_no,
                carrier,
                raw_code,
                raw_label,
                occurred_at,
                received_at,
                imported_at,
                import_batch_id,
                location,
                description,
            ],
        )

    def scan_rows(self, tracking_no: str) -> list[dict[str, Any]]:
        return self._rows(
            """
            SELECT scan_id, tracking_no, carrier, raw_code, raw_label, occurred_at,
                   received_at, imported_at, import_batch_id, location, description
            FROM scan_events WHERE tracking_no = ?
            ORDER BY occurred_at, received_at, scan_id
            """,
            [tracking_no],
        )

    def all_scan_rows(self) -> list[dict[str, Any]]:
        return self._rows(
            """
            SELECT scan_id, tracking_no, carrier, raw_code, raw_label, occurred_at,
                   received_at, imported_at, import_batch_id, location, description
            FROM scan_events ORDER BY tracking_no, occurred_at, received_at, scan_id
            """
        )

    def duplicate_attempts(self, tracking_no: str) -> list[dict[str, Any]]:
        rows = self._rows(
            """
            SELECT scan_id, reason, attempted_at, batch_id
            FROM scan_attempts
            WHERE tracking_no = ? AND outcome = 'DUPLICATE'
            ORDER BY attempted_at DESC
            """,
            [tracking_no],
        )
        return [
            {
                "scan_id": row["scan_id"],
                "reason": row["reason"],
                "attempted_at": iso_bj(row["attempted_at"]),
                "batch_id": row["batch_id"],
            }
            for row in rows
        ]

    def import_batches(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._rows(
            """
            SELECT id, source, carrier, imported_at, received_count, inserted_count,
                   duplicate_count, rejected_count
            FROM import_batches ORDER BY imported_at DESC, id DESC LIMIT ?
            """,
            [limit],
        )
        return [
            {
                **row,
                "imported_at": iso_bj(row["imported_at"]),
            }
            for row in rows
        ]

    def batch_detail(self, batch_id: int) -> dict[str, Any] | None:
        rows = self._rows(
            """
            SELECT id, source, carrier, imported_at, received_count, inserted_count,
                   duplicate_count, rejected_count
            FROM import_batches WHERE id = ?
            """,
            [batch_id],
        )
        if not rows:
            return None
        row = rows[0]
        row["imported_at"] = iso_bj(row["imported_at"])
        attempts = self._rows(
            """
            SELECT scan_id, tracking_no, outcome, reason, attempted_at
            FROM scan_attempts WHERE batch_id = ? ORDER BY id
            """,
            [batch_id],
        )
        row["attempts"] = [
            {**item, "attempted_at": iso_bj(item["attempted_at"])} for item in attempts
        ]
        return row

    # ---------- analysis ----------

    def analyze_package(
        self,
        package: dict[str, Any],
        as_of: datetime,
        mappings: dict[tuple[str, str], str] | None = None,
        holidays: dict | None = None,
    ) -> Analysis:
        mappings = mappings if mappings is not None else self.mapping_dict()
        holidays = holidays if holidays is not None else self.holiday_dict()
        events = self.scan_rows(package["tracking_no"])
        return reconstruct(package, events, mappings, holidays, as_of)

    def analyze_all(self, as_of: datetime) -> tuple[list[dict[str, Any]], dict[str, Analysis]]:
        packages = self.packages_raw()
        mappings = self.mapping_dict()
        holidays = self.holiday_dict()
        analyses: dict[str, Analysis] = {}
        summaries: list[dict[str, Any]] = []
        for pkg in packages:
            analysis = self.analyze_package(pkg, as_of, mappings, holidays)
            alerts = compute_alerts(analysis, as_of, holidays)
            summary = summarize(analysis, as_of, holidays, alerts)
            analyses[pkg["tracking_no"]] = analysis
            summaries.append(summary)
        return summaries, analyses

    def package_detail(self, tracking_no: str, as_of: datetime) -> dict[str, Any] | None:
        pkg = self.package_raw(tracking_no)
        if not pkg:
            return None
        holidays = self.holiday_dict()
        analysis = self.analyze_package(pkg, as_of, holidays=holidays)
        alerts = compute_alerts(analysis, as_of, holidays)
        summary = summarize(analysis, as_of, holidays, alerts)
        from .domain import analysis_to_detail

        detail = analysis_to_detail(analysis, summary, as_of, holidays)
        detail["duplicate_attempts"] = self.duplicate_attempts(tracking_no)
        detail["persisted_alert_history"] = self.alert_history(tracking_no)
        return detail

    # ---------- alert lifecycle ----------

    def current_alerts(self) -> list[dict[str, Any]]:
        return self._rows(
            """
            SELECT tracking_no, alert_type, state, reason, details_json, first_seen_at,
                   last_changed_at, last_evaluated_at, resolved_at
            FROM alert_current ORDER BY tracking_no, alert_type
            """
        )

    def alert_history(self, tracking_no: str | None = None) -> list[dict[str, Any]]:
        sql = """
            SELECT id, tracking_no, alert_type, change_type, from_state, to_state,
                   reason, details_json, changed_at
            FROM alert_history
        """
        params: list[Any] = []
        if tracking_no:
            sql += " WHERE tracking_no = ?"
            params.append(tracking_no)
        sql += " ORDER BY changed_at DESC, id DESC"
        rows = self._rows(sql, params)
        return [
            {
                **row,
                "changed_at": iso_bj(row["changed_at"]),
                "details": json.loads(row["details_json"]) if row["details_json"] else None,
            }
            for row in rows
        ]

    def _write_alert_history(
        self,
        tracking_no: str,
        alert_type: str,
        change_type: str,
        from_state: str | None,
        to_state: str,
        reason: str,
        details: dict | None,
        changed_at: datetime,
    ) -> None:
        self._execute(
            """
            INSERT INTO alert_history
            (id, tracking_no, alert_type, change_type, from_state, to_state, reason,
             details_json, changed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                self._next_seq("alert_history_seq"),
                tracking_no,
                alert_type,
                change_type,
                from_state,
                to_state,
                reason,
                json.dumps(details, ensure_ascii=False, default=str) if details else None,
                changed_at,
            ],
        )

    def recalculate(
        self,
        as_of: datetime | None = None,
        only_tracking_no: str | None = None,
        history_at: datetime | None = None,
    ) -> dict[str, Any]:
        """重算并持久化当前告警；每个包裹每种告警只保留一行当前状态。

        history_at 用于演示时把变化历史记在模拟观察时刻，而不是真实执行时刻。
        """
        as_of = as_of or now_beijing()
        history_time = history_at or as_of
        packages = self.packages_raw()
        if only_tracking_no:
            packages = [p for p in packages if p["tracking_no"] == only_tracking_no]
        mappings = self.mapping_dict()
        holidays = self.holiday_dict()

        computed: dict[tuple[str, str], dict[str, Any]] = {}
        computed_details: dict[tuple[str, str], dict[str, Any]] = {}
        for pkg in packages:
            analysis = self.analyze_package(pkg, as_of, mappings, holidays)
            for alert in compute_alerts(analysis, as_of, holidays):
                key = (pkg["tracking_no"], alert["type"])
                computed[key] = alert
                computed_details[key] = alert

        current_rows = self.current_alerts()
        current: dict[tuple[str, str], dict[str, Any]] = {
            (row["tracking_no"], row["alert_type"]): row for row in current_rows
        }
        allowed = {p["tracking_no"] for p in packages}
        created = updated = cleared = unchanged = 0

        for key, alert in computed.items():
            tracking_no, alert_type = key
            details = {k: v for k, v in alert.items() if k != "reason"}
            details_json = json.dumps(details, ensure_ascii=False, sort_keys=True, default=str)
            reason = alert["reason"]
            existing = current.get(key)
            if existing is None or existing["state"] != "ACTIVE":
                change = "CREATED" if existing is None else "REOPENED"
                first_seen = existing["first_seen_at"] if existing and existing["first_seen_at"] else history_time
                self._execute(
                    """
                    INSERT INTO alert_current
                    (tracking_no, alert_type, state, reason, details_json, first_seen_at,
                     last_changed_at, last_evaluated_at, resolved_at)
                    VALUES (?, ?, 'ACTIVE', ?, ?, ?, ?, ?, NULL)
                    ON CONFLICT (tracking_no, alert_type) DO UPDATE SET
                        state = 'ACTIVE', reason = excluded.reason,
                        details_json = excluded.details_json,
                        first_seen_at = excluded.first_seen_at,
                        last_changed_at = excluded.last_changed_at,
                        last_evaluated_at = excluded.last_evaluated_at,
                        resolved_at = NULL
                    """,
                    [tracking_no, alert_type, reason, details_json, first_seen, history_time, as_of],
                )
                self._write_alert_history(
                    tracking_no,
                    alert_type,
                    change,
                    existing["state"] if existing else None,
                    "ACTIVE",
                    reason,
                    details,
                    history_time,
                )
                current[key] = {
                    "tracking_no": tracking_no,
                    "alert_type": alert_type,
                    "state": "ACTIVE",
                    "reason": reason,
                    "details_json": details_json,
                    "first_seen_at": first_seen,
                    "last_changed_at": history_time,
                    "last_evaluated_at": as_of,
                    "resolved_at": None,
                }
                created += 1
            else:
                old_details = existing.get("details_json")
                if existing["reason"] != reason or old_details != details_json:
                    self._execute(
                        """
                        UPDATE alert_current SET reason = ?, details_json = ?,
                            last_changed_at = ?, last_evaluated_at = ?
                        WHERE tracking_no = ? AND alert_type = ?
                        """,
                        [reason, details_json, history_time, as_of, tracking_no, alert_type],
                    )
                    self._write_alert_history(
                        tracking_no,
                        alert_type,
                        "UPDATED",
                        "ACTIVE",
                        "ACTIVE",
                        reason,
                        details,
                        history_time,
                    )
                    existing["reason"] = reason
                    existing["details_json"] = details_json
                    existing["last_changed_at"] = history_time
                    updated += 1
                else:
                    self._execute(
                        """
                        UPDATE alert_current SET last_evaluated_at = ?
                        WHERE tracking_no = ? AND alert_type = ?
                        """,
                        [as_of, tracking_no, alert_type],
                    )
                    unchanged += 1

        active_keys = {
            key
            for key, row in current.items()
            if row["state"] == "ACTIVE" and row["tracking_no"] in allowed
        }
        for key in active_keys - set(computed):
            tracking_no, alert_type = key
            self._execute(
                """
                UPDATE alert_current SET state = 'CLEARED',
                    reason = ?, last_changed_at = ?, last_evaluated_at = ?, resolved_at = ?
                WHERE tracking_no = ? AND alert_type = ?
                """,
                [
                    "重新计算后告警已解除",
                    history_time,
                    as_of,
                    history_time,
                    tracking_no,
                    alert_type,
                ],
            )
            self._write_alert_history(
                tracking_no,
                alert_type,
                "CLEARED",
                "ACTIVE",
                "CLEARED",
                "重新计算后告警已解除",
                None,
                history_time,
            )
            cleared += 1

        return {
            "as_of": iso_bj(as_of),
            "active_alerts": len(computed),
            "created": created,
            "updated": updated,
            "cleared": cleared,
            "unchanged": unchanged,
        }


_repositories: dict[str, Repository] = {}
_repository_lock = threading.Lock()


def get_repository(db_path: str) -> Repository:
    with _repository_lock:
        if db_path not in _repositories:
            _repositories[db_path] = Repository(db_path)
        return _repositories[db_path]
