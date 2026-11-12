import React from "react";
import {
  AlertTriangle,
  ChevronRight,
  Filter,
  PackageSearch,
  Search,
  TimerReset,
  X,
} from "lucide-react";
import { AlertPill, EmptyState, Spinner, StageTrack, StatusPill } from "./Shared";
import { datePart, hours, timePart, weekdayPart } from "../utils";

function StatusSelect({ label, value, onChange, options, placeholder }) {
  return (
    <label className="select-wrap">
      <span className="sr-only">{label}</span>
      <select value={value || ""} onChange={(event) => onChange(event.target.value)}>
        <option value="">{placeholder}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function PackageTable({
  items,
  filters,
  onFilterChange,
  carriers,
  statusCatalog,
  onSelect,
  loading,
  total,
}) {
  const alertType = filters.alertType;
  return (
    <section className="panel package-panel" id="monitor">
      <div className="panel-heading package-heading">
        <div>
          <span className="eyebrow">LIVE TRAJECTORY</span>
          <h2>包裹轨迹与超时清单</h2>
          <p>{total} 个包裹按告警和等待时长排序；点击任意一行还原完整轨迹。</p>
        </div>
        <div className="heading-count">
          <strong>{items.length}</strong>
          <span>当前筛选</span>
        </div>
      </div>

      <div className="filter-row">
        <label className="search-box">
          <Search size={15} />
          <input
            value={filters.q || ""}
            onChange={(event) => onFilterChange({ ...filters, q: event.target.value })}
            placeholder="搜索运单号、收件人、路线…"
            aria-label="搜索包裹"
          />
          {filters.q ? (
            <button
              type="button"
              className="clear-search"
              onClick={() => onFilterChange({ ...filters, q: "" })}
              aria-label="清空搜索"
            >
              <X size={13} />
            </button>
          ) : null}
        </label>
        <StatusSelect
          label="承运商"
          value={filters.carrier}
          onChange={(value) => onFilterChange({ ...filters, carrier: value })}
          options={carriers.map((carrier) => ({ value: carrier.code, label: carrier.name }))}
          placeholder="全部承运商"
        />
        <StatusSelect
          label="包裹状态"
          value={filters.status}
          onChange={(value) => onFilterChange({ ...filters, status: value })}
          options={statusCatalog.map((status) => ({
            value: status.code,
            label: status.label,
          }))}
          placeholder="全部状态"
        />
        <button
          type="button"
          className={`filter-toggle ${filters.alertOnly ? "active" : ""}`}
          onClick={() => onFilterChange({ ...filters, alertOnly: !filters.alertOnly })}
        >
          <Filter size={14} />
          仅看告警
        </button>
        {alertType ? (
          <button
            type="button"
            className="active-filter-chip"
            onClick={() => onFilterChange({ ...filters, alertType: null, alertOnly: false })}
          >
            {alertType === "STALLED" ? <TimerReset size={13} /> : <AlertTriangle size={13} />}
            {alertType === "STALLED" ? "停滞" : "整体超时"}
            <X size={12} />
          </button>
        ) : null}
      </div>

      <div className="table-scroll">
        <table className="package-table">
          <thead>
            <tr>
              <th>包裹</th>
              <th>承运商</th>
              <th>路线</th>
              <th>当前状态</th>
              <th>工作耗时</th>
              <th>最近进展</th>
              <th>告警 / 异常</th>
              <th aria-label="打开轨迹" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={8}>
                  <div className="table-loading">
                    <Spinner label="正在按发生时间还原轨迹…" />
                  </div>
                </td>
              </tr>
            ) : null}
            {!loading && items.length === 0 ? (
              <tr>
                <td colSpan={8}>
                  <EmptyState
                    icon={<PackageSearch size={24} />}
                    title="没有符合条件的包裹"
                    description="调整承运商、状态或告警筛选后再试。"
                  />
                </td>
              </tr>
            ) : null}
            {!loading
              ? items.map((item) => {
                  const delivered = item.status === "DELIVERED";
                  const completed = delivered || item.status === "RETURNED" || item.status === "CANCELLED";
                  const primaryAlert = item.alerts[0];
                  return (
                    <tr
                      key={item.tracking_no}
                      className={`package-row ${item.active_alert_count ? "has-alert" : ""}`}
                      onClick={() => onSelect(item.tracking_no)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          onSelect(item.tracking_no);
                        }
                      }}
                      tabIndex={0}
                      role="button"
                    >
                      <td>
                        <div className="package-identity">
                          <span className="package-icon">
                            <PackageSearch size={16} />
                          </span>
                          <span>
                            <strong>{item.tracking_no}</strong>
                            <small>{item.display_name || "未命名包裹"}</small>
                          </span>
                        </div>
                      </td>
                      <td>
                        <span className="carrier-tag">
                          <b>{item.carrier}</b>
                          {item.carrier_name}
                        </span>
                      </td>
                      <td>
                        <span className="route-cell">
                          {item.origin || "—"}
                          <ChevronRight size={13} />
                          {item.destination || "—"}
                        </span>
                      </td>
                      <td>
                        <div className="status-cell">
                          <StatusPill
                            status={item.status}
                            label={item.status_label}
                            catalog={statusCatalog}
                            compact
                          />
                          <StageTrack timeline={[]} status={item.status} compact />
                        </div>
                      </td>
                      <td>
                        <div className="duration-cell">
                          {completed ? (
                            <>
                              <strong>
                                {delivered ? hours(item.overall_business_hours, 1) : "—"}
                              </strong>
                              <small>{delivered ? "全程" : "已结束"}</small>
                            </>
                          ) : (
                            <>
                              <strong>{hours(item.waiting_business_hours, 1)}</strong>
                              <small>等待进展</small>
                            </>
                          )}
                        </div>
                      </td>
                      <td>
                        <div className="last-scan-cell">
                          <strong>
                            {item.last_scan_at
                              ? `${datePart(item.last_scan_at)} ${timePart(item.last_scan_at)}`
                              : "尚无扫描"}
                          </strong>
                          <small>
                            {item.last_scan_at
                              ? `${weekdayPart(item.last_scan_at)} · ${item.events_count} 条有效去重扫描`
                              : "等待承运商回传"}
                          </small>
                        </div>
                      </td>
                      <td>
                        <div className="alert-cell">
                          {primaryAlert ? (
                            <AlertPill
                              type={primaryAlert.type}
                              hoursValue={
                                primaryAlert.type === "STALLED"
                                  ? item.waiting_business_hours
                                  : primaryAlert.hours
                              }
                            />
                          ) : null}
                          {item.active_alert_count > 1 ? (
                            <span className="more-alerts">+{item.active_alert_count - 1}</span>
                          ) : null}
                          {!primaryAlert ? <span className="no-alert">—</span> : null}
                          {item.anomaly_count ? (
                            <span className="anomaly-badge">
                              <AlertTriangle size={12} />
                              {item.anomaly_count} 异常
                            </span>
                          ) : null}
                          {item.late_scan_count ? (
                            <span className="late-badge">{item.late_scan_count} 晚到</span>
                          ) : null}
                        </div>
                      </td>
                      <td className="row-chevron">
                        <ChevronRight size={17} />
                      </td>
                    </tr>
                  );
                })
              : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
