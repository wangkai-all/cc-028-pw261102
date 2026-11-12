import React, { useState } from "react";
import {
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  Clock3,
  PlusCircle,
  ShieldCheck,
} from "lucide-react";
import { AlertIcon, EmptyState, SegmentsPanel } from "./Shared";
import { datePart, hours, timePart } from "../utils";

function AlertCard({ alert, onSelect, onSupplement, supplementing }) {
  const [expanded, setExpanded] = useState(false);
  const isStalled = alert.type === "STALLED";

  return (
    <article className={`alert-card ${isStalled ? "is-stalled" : "is-timeout"} ${expanded ? "expanded" : ""}`}>
      <span className="alert-accent" aria-hidden="true" />
      <button
        type="button"
        className="alert-card-head"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
      >
        <span className="alert-icon">
          <AlertIcon type={alert.type} size={18} />
        </span>
        <span className="alert-head-copy">
          <span className="alert-title-line">
            <strong>{alert.label}</strong>
            <span className="alert-hours">{hours(alert.hours, 2)}</span>
          </span>
          <small>
            {alert.tracking_no} · {alert.display_name || alert.carrier_name}
          </small>
        </span>
        {expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
      </button>

      <div className="alert-card-body">
        <p className="alert-reason">{alert.reason}</p>
        <div className="alert-route">
          <span>{alert.origin || "—"}</span>
          <span className="route-line" />
          <span>{alert.destination || "—"}</span>
          <span className="alert-status">{alert.package_status_label}</span>
        </div>
        {alert.start ? (
          <div className="alert-dates">
            <span>
              从 {datePart(alert.start)} {timePart(alert.start)}
            </span>
            <span>
              至 {datePart(alert.end)} {timePart(alert.end)}
            </span>
          </div>
        ) : null}
        {expanded ? <SegmentsPanel alert={alert} /> : null}
      </div>

      <div className="alert-card-actions">
        <button
          type="button"
          className="text-button with-icon"
          onClick={() => onSelect(alert.tracking_no)}
        >
          查看轨迹 <ArrowUpRight size={13} />
        </button>
        {isStalled && alert.package_status !== "DELIVERED" ? (
          <button
            type="button"
            className="mini-button"
            onClick={() => onSupplement(alert.tracking_no)}
            disabled={supplementing === alert.tracking_no}
          >
            <PlusCircle size={13} />
            {supplementing === alert.tracking_no ? "补录中" : "补录缺失扫描"}
          </button>
        ) : null}
        {!expanded ? (
          <button
            type="button"
            className="text-button subtle"
            onClick={() => setExpanded(true)}
          >
            看计时明细
          </button>
        ) : null}
      </div>
    </article>
  );
}

export function AlertRail({ alerts, asOf, onSelect, onSupplement, supplementing }) {
  return (
    <section className="alert-rail" id="alert-rail" aria-label="超时与停滞清单">
      <div className="rail-heading">
        <div>
          <span className="eyebrow">ACTIVE ALERTS</span>
          <h2>告警清单</h2>
        </div>
        <span className="rail-count">{alerts.length}</span>
      </div>
      <div className="rail-note">
        <Clock3 size={13} />
        观察时刻 {datePart(asOf)} {timePart(asOf)}，之后的扫描未参与判断
      </div>

      <div className="rail-list">
        {alerts.length ? (
          alerts.map((alert) => (
            <AlertCard
              key={alert.id}
              alert={alert}
              onSelect={onSelect}
              onSupplement={onSupplement}
              supplementing={supplementing}
            />
          ))
        ) : (
          <EmptyState
            icon={<ShieldCheck size={25} />}
            title="当前没有活跃告警"
            description="停滞与整体超时均已解除，或观察时刻早于阈值触发。"
          />
        )}
      </div>
      <div className="rail-footer">
        <ShieldCheck size={13} />
        同一包裹同一种告警只保留一个当前状态，变化写入历史。
      </div>
    </section>
  );
}
