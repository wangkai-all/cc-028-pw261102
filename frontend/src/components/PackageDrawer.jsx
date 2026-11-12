import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  ChevronDown,
  ChevronUp,
  Clock3,
  Copy,
  Info,
  MapPin,
  PlusCircle,
  Radio,
  RotateCcw,
  X,
} from "lucide-react";
import {
  AlertIcon,
  EmptyState,
  SegmentsPanel,
  Spinner,
  StageTrack,
  StatusPill,
} from "./Shared";
import {
  datePart,
  dateTimePart,
  fullDate,
  hours,
  hoursLong,
  importChangeLabel,
  relativeReceived,
  timePart,
  weekdayPart,
} from "../utils";

function DetailMetric({ label, value, hint, tone }) {
  return (
    <div className={`detail-metric ${tone || ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {hint ? <small>{hint}</small> : null}
    </div>
  );
}

function DrawerAlert({ alert, onSupplement, supplementing }) {
  const [expanded, setExpanded] = useState(true);
  const isStalled = alert.type === "STALLED";
  return (
    <article className={`drawer-alert ${isStalled ? "is-stalled" : "is-timeout"}`}>
      <button
        type="button"
        className="drawer-alert-head"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
      >
        <span className="alert-icon">
          <AlertIcon type={alert.type} size={17} />
        </span>
        <div>
          <span className="drawer-alert-title">
            <strong>{alert.label}</strong>
            <b>{hoursLong(alert.hours)}</b>
          </span>
          <p>{alert.reason}</p>
        </div>
        {expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
      </button>
      {expanded ? (
        <div className="drawer-alert-detail">
          <SegmentsPanel alert={alert} />
          {isStalled && alert.package_status !== "DELIVERED" ? (
            <button
              type="button"
              className="mini-button supplement-button"
              onClick={() => onSupplement(alert.tracking_no || null)}
              disabled={supplementing}
            >
              <PlusCircle size={13} />
              {supplementing ? "补录中" : "补录缺失扫描并重算"}
            </button>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

function TimelineEvent({ event, statusCatalog }) {
  const anomalous = Boolean(event.anomaly_code);
  return (
    <div className={`timeline-event ${event.is_effective ? "effective" : "non-effective"} ${anomalous ? "anomalous" : ""}`}>
      <div className="timeline-when">
        <span>{datePart(event.occurred_at)}</span>
        <strong>{timePart(event.occurred_at)}</strong>
        <small>{weekdayPart(event.occurred_at)}</small>
      </div>
      <div className="timeline-axis" aria-hidden="true">
        <span className={`timeline-dot ${anomalous ? "anomalous" : event.is_effective ? "effective" : ""}`} />
      </div>
      <div className="timeline-card">
        <div className="timeline-card-head">
          <StatusPill
            status={event.mapped_status || "PENDING"}
            label={event.mapped_label}
            catalog={statusCatalog}
            compact
          />
          <span className="raw-code-chip">{event.raw_code}</span>
          {event.is_effective ? (
            <span className="effective-badge">
              <Check size={11} /> 有效进展
            </span>
          ) : (
            <span className="inactive-badge">未推进</span>
          )}
          {event.late_arrival ? (
            <span className="late-badge">{relativeReceived(event.received_delay_hours)}</span>
          ) : null}
        </div>
        <p className="timeline-description">{event.description || event.raw_label}</p>
        <div className="timeline-meta">
          <span>
            <MapPin size={12} /> {event.location || "未提供地点"}
          </span>
          <span>
            接收 {dateTimePart(event.received_at)}
          </span>
          <span>批次 #{event.import_batch_id ?? "—"}</span>
        </div>
        {event.anomaly_reason ? (
          <div className="anomaly-callout">
            <AlertTriangle size={13} />
            <div>
              <strong>{event.anomaly_code === "UNKNOWN_STATUS" ? "未知状态" : "异常扫描"}</strong>
              <span>{event.anomaly_reason}</span>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function PackageDrawer({
  detail,
  loading,
  onClose,
  onSupplement,
  supplementing,
  statusCatalog,
}) {
  useEffect(() => {
    const handler = (event) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const summary = detail?.summary;
  const packageInfo = detail?.package;
  const alerts = detail?.alerts || [];
  const business = detail?.business_clock;
  const anomalies = detail?.anomalies || [];
  const duplicates = detail?.duplicate_attempts || [];
  const history = detail?.persisted_alert_history || [];
  const hasStall = alerts.some((alert) => alert.type === "STALLED");

  return (
    <div className="drawer-layer" role="presentation">
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="package-drawer" role="dialog" aria-modal="true" aria-label="包裹轨迹详情">
        <div className="drawer-header">
          <div className="drawer-title-wrap">
            <span className="eyebrow">PACKAGE TRACE</span>
            <h2>{packageInfo?.tracking_no || "读取轨迹…"}</h2>
            {summary ? (
              <div className="drawer-subline">
                <StatusPill
                  status={summary.status}
                  label={summary.status_label}
                  catalog={statusCatalog}
                />
                <span>{packageInfo?.carrier_name}</span>
                <span>
                  {packageInfo?.origin || "—"} <ArrowRight size={12} /> {packageInfo?.destination || "—"}
                </span>
              </div>
            ) : null}
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="关闭轨迹详情">
            <X size={18} />
          </button>
        </div>

        {loading || !detail ? (
          <div className="drawer-loading">
            <Spinner label="正在还原时间线…" />
          </div>
        ) : (
          <div className="drawer-body">
            <div className="package-name-bar">
              <span className="package-avatar">{packageInfo.display_name?.slice(0, 1) || "包"}</span>
              <div>
                <strong>{packageInfo.display_name || "未命名包裹"}</strong>
                <small>
                  观察时刻 {fullDate(detail.as_of)} {timePart(detail.as_of)} · {detail.timeline.length} 条去重扫描
                </small>
              </div>
              {hasStall ? (
                <button
                  type="button"
                  className="mini-button"
                  onClick={() => onSupplement(summary.tracking_no)}
                  disabled={supplementing}
                >
                  <PlusCircle size={13} />
                  {supplementing ? "补录中" : "补录缺失扫描"}
                </button>
              ) : null}
            </div>

            <div className="detail-metrics">
              <DetailMetric
                label="当前停留"
                value={hours(summary.waiting_business_hours, 1)}
                hint={summary.is_open ? "自最近有效进展" : "已结束，无等待计时"}
              />
              <DetailMetric
                label="全程工作耗时"
                value={hours(summary.overall_business_hours, 1)}
                hint="揽收至签收 / 观察时刻"
              />
              <DetailMetric
                label="活跃告警"
                value={alerts.length}
                hint="同类型仅保留一条"
                tone={alerts.length ? "warn" : ""}
              />
              <DetailMetric
                label="异常 / 晚到"
                value={`${anomalies.length} / ${summary.late_scan_count}`}
                hint="异常不推进当前进度"
                tone={anomalies.length ? "danger" : ""}
              />
            </div>

            <div className="drawer-section">
              <div className="drawer-section-head">
                <h3>进度轨迹</h3>
                <span>按发生时间推进，签收后不回退</span>
              </div>
              <StageTrack timeline={detail.timeline} status={summary.status} />
            </div>

            {alerts.length ? (
              <div className="drawer-section">
                <div className="drawer-section-head">
                  <h3>告警与计时区间</h3>
                  <span>点击展开逐段工作时段</span>
                </div>
                <div className="drawer-alert-list">
                  {alerts.map((alert) => (
                    <DrawerAlert
                      key={alert.type}
                      alert={{ ...alert, tracking_no: summary.tracking_no }}
                      onSupplement={onSupplement}
                      supplementing={Boolean(supplementing)}
                    />
                  ))}
                </div>
              </div>
            ) : null}

            <div className="drawer-section">
              <div className="drawer-section-head">
                <h3>扫描时间线</h3>
                <span>接收时间只说明数据何时到达</span>
              </div>
              <div className="timeline-note">
                <Radio size={13} />
                排序键为发生时间；晚到补录的早期扫描会插入原位置。错过观察时刻的扫描不参与判断。
              </div>
              {detail.timeline.length ? (
                <div className="timeline-list">
                  {detail.timeline.map((event) => (
                    <TimelineEvent
                      key={event.scan_id}
                      event={event}
                      statusCatalog={statusCatalog}
                    />
                  ))}
                </div>
              ) : (
                <EmptyState
                  icon={<Clock3 size={22} />}
                  title="还没有扫描"
                  description="承运商扫描导入后，轨迹会按发生时间出现在这里。"
                />
              )}
            </div>

            {duplicates.length || summary.late_scan_count ? (
              <div className="drawer-section">
                <div className="drawer-section-head">
                  <h3>去重与补录</h3>
                  <span>相同扫描编号只保留首条</span>
                </div>
                <div className="dedupe-row">
                  <span className="dedupe-stat">
                    <Copy size={14} />
                    <b>{duplicates.length}</b> 条重复扫描已跳过
                  </span>
                  <span className="dedupe-stat">
                    <Radio size={14} />
                    <b>{summary.late_scan_count}</b> 条晚到扫描已归位
                  </span>
                  <span className="dedupe-stat">
                    <Clock3 size={14} />
                    <b>{summary.ignored_future_count}</b> 条扫描晚于观察时刻
                  </span>
                </div>
                {duplicates.length ? (
                  <div className="duplicate-list">
                    {duplicates.slice(0, 6).map((item) => (
                      <span key={`${item.scan_id}-${item.attempted_at}`}>
                        <b>{item.scan_id}</b>
                        {item.reason}
                        <small>批次 #{item.batch_id}</small>
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}

            <div className="drawer-section">
              <div className="drawer-section-head">
                <h3>告警变化历史</h3>
                <span>当前状态唯一，变化留痕</span>
              </div>
              {history.length ? (
                <div className="history-list">
                  {history.map((item) => (
                    <div className="history-item" key={item.id}>
                      <span className={`history-change history-${item.change_type.toLowerCase()}`}>
                        {importChangeLabel(item.change_type)}
                      </span>
                      <div>
                        <strong>
                          {item.alert_type === "STALLED" ? "停滞" : "整体超时"}
                          <small> {item.reason}</small>
                        </strong>
                        <span>{dateTimePart(item.changed_at)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="history-empty">
                  <Info size={14} />
                  还没有持久化变化。导入扫描或点击“重算告警”后，新增、更新、解除都会记录。
                </div>
              )}
            </div>

            {business?.waiting?.skipped?.length ? (
              <div className="drawer-footnote">
                <RotateCcw size={13} />
                等待计时已跳过 {business.waiting.skipped.length} 个周末 / 节假日。
              </div>
            ) : null}
          </div>
        )}
      </aside>
    </div>
  );
}
