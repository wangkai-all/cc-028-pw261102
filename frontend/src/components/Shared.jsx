import React from "react";
import {
  AlertCircle,
  AlertTriangle,
  Check,
  Clock3,
  Info,
  PauseCircle,
  RotateCcw,
  X,
} from "lucide-react";
import { datePart, hours, hoursLong, statusTone, timePart } from "../utils";

const STAGES = [
  { code: "PICKED_UP", label: "揽收", rank: 10 },
  { code: "IN_TRANSIT", label: "运输", rank: 20 },
  { code: "ARRIVED", label: "到站", rank: 30 },
  { code: "OUT_FOR_DELIVERY", label: "派送", rank: 40 },
  { code: "DELIVERED", label: "签收", rank: 50 },
];

const RANKS = Object.fromEntries(STAGES.map((stage) => [stage.code, stage.rank]));

export function StatusPill({ status, label, catalog, compact = false }) {
  const meta = catalog?.find((item) => item.code === status);
  const text = label || meta?.label || status;
  return (
    <span className={`status-pill status-${statusTone(status)} ${compact ? "compact" : ""}`}>
      <span className="status-dot" aria-hidden="true" />
      {text}
    </span>
  );
}

export function AlertPill({ type, hoursValue, compact = false }) {
  const isTimeout = type === "OVERALL_TIMEOUT";
  return (
    <span className={`alert-pill ${isTimeout ? "alert-overall" : "alert-stalled"} ${compact ? "compact" : ""}`}>
      {isTimeout ? <Clock3 size={13} /> : <PauseCircle size={13} />}
      {isTimeout ? "整体超时" : "停滞"}
      {hoursValue !== undefined && hoursValue !== null ? (
        <b>{hours(hoursValue, 1)}</b>
      ) : null}
    </span>
  );
}

export function AlertIcon({ type, size = 18 }) {
  return type === "OVERALL_TIMEOUT" ? <Clock3 size={size} /> : <PauseCircle size={size} />;
}

export function StageTrack({ timeline = [], status, compact = false }) {
  const effectiveRanks = timeline
    .filter((event) => event.is_effective && RANKS[event.mapped_status])
    .map((event) => RANKS[event.mapped_status]);
  const currentRank = RANKS[status] || 0;
  const reachedRank = Math.max(currentRank, ...effectiveRanks, 0);
  const terminal = status === "RETURNED" || status === "CANCELLED";

  if (compact) {
    return (
      <div className={`stage-bars ${terminal ? "terminal" : ""}`} aria-label={`进度：${reachedRank}`}>
        {STAGES.map((stage) => (
          <span
            key={stage.code}
            className={`stage-bar ${reachedRank >= stage.rank ? "reached" : ""} ${
              currentRank === stage.rank && !terminal ? "current" : ""
            }`}
            title={stage.label}
          />
        ))}
      </div>
    );
  }

  return (
    <div className={`stage-track ${terminal ? "is-terminal" : ""}`}>
      {STAGES.map((stage, index) => {
        const reached = reachedRank >= stage.rank;
        const current = currentRank === stage.rank && !terminal;
        return (
          <React.Fragment key={stage.code}>
            <div className={`stage-node ${reached ? "reached" : ""} ${current ? "current" : ""}`}>
              <span className="stage-circle">{reached ? <Check size={12} strokeWidth={3} /> : index + 1}</span>
              <span className="stage-label">{stage.label}</span>
            </div>
            {index < STAGES.length - 1 ? (
              <span className={`stage-line ${reachedRank >= STAGES[index + 1].rank ? "reached" : ""}`} />
            ) : null}
          </React.Fragment>
        );
      })}
      {terminal ? (
        <div className={`terminal-node terminal-${statusTone(status)}`}>
          {status === "RETURNED" ? <RotateCcw size={13} /> : <X size={13} />}
          {status === "RETURNED" ? "退回结束" : "运单取消"}
        </div>
      ) : null}
    </div>
  );
}

export function SegmentsPanel({ alert, title = "计时明细" }) {
  const segments = alert?.segments || [];
  const skipped = alert?.skipped || [];
  const total = alert?.hours ?? 0;
  const maxHours = Math.max(1, ...segments.map((segment) => Number(segment.hours) || 0));

  return (
    <div className="segments-panel">
      <div className="segments-head">
        <div>
          <span className="segments-title">{title}</span>
          <span className="segments-sub">
            仅累计北京时间 09:00–18:00 的工作时段
          </span>
        </div>
        <strong>{hoursLong(total)}</strong>
      </div>
      {segments.length ? (
        <div className="segment-list">
          {segments.map((segment) => (
            <div className="segment-row" key={`${segment.date}-${segment.start}`}>
              <span className="segment-date">{datePart(segment.start)}</span>
              <span className="segment-time">
                {timePart(segment.start)}–{timePart(segment.end)}
              </span>
              <span className="segment-bar" aria-hidden="true">
                <i style={{ width: `${Math.max(3, (Number(segment.hours) / maxHours) * 100)}%` }} />
              </span>
              <span className="segment-hours">{hours(segment.hours)}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="segment-empty">这个区间内没有可累计的工作时段。</div>
      )}
      {skipped.length ? (
        <div className="skipped-list">
          <span className="skipped-title">
            <Info size={12} /> 已跳过
          </span>
          {skipped.map((item) => (
            <span className="skip-chip" key={item.date}>
              {datePart(`${item.date}T00:00:00+08:00`)} · {item.reason}
            </span>
          ))}
        </div>
      ) : null}
      {alert?.start && alert?.end ? (
        <div className="segments-range">
          计算区间 {datePart(alert.start)} {timePart(alert.start)} → {datePart(alert.end)}{" "}
          {timePart(alert.end)}
        </div>
      ) : null}
    </div>
  );
}

export function Spinner({ label = "加载中" }) {
  return (
    <span className="spinner-wrap">
      <span className="spinner" />
      {label}
    </span>
  );
}

export function EmptyState({ icon = <Info size={22} />, title, description }) {
  return (
    <div className="empty-state">
      <span className="empty-icon">{icon}</span>
      <strong>{title}</strong>
      {description ? <p>{description}</p> : null}
    </div>
  );
}

export function Toast({ toast, onClose }) {
  if (!toast) return null;
  const Icon = toast.type === "error" ? AlertCircle : toast.type === "warn" ? AlertTriangle : Check;
  return (
    <div className={`toast toast-${toast.type || "success"}`} role="status">
      <span className="toast-icon">
        <Icon size={16} />
      </span>
      <span className="toast-message">{toast.message}</span>
      <button type="button" className="icon-button tiny" onClick={onClose} aria-label="关闭提示">
        <X size={14} />
      </button>
    </div>
  );
}
