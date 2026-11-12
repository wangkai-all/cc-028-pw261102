import React from "react";
import {
  ArrowRight,
  CircleAlert,
  Clock3,
  PackageOpen,
  PauseCircle,
  ScanSearch,
  ShieldAlert,
  Sparkles,
  TriangleAlert,
} from "lucide-react";

function MiniMetric({ label, value, tone }) {
  return (
    <span className={`mini-metric ${tone || ""}`}>
      <b>{value}</b>
      {label}
    </span>
  );
}

export function StatCards({ overview, onFocusAlerts, onFilterAlert }) {
  const totals = overview.totals;
  return (
    <section className="stat-grid" aria-label="包裹与告警概览">
      <article className="stat-card stat-attention">
        <div className="stat-topline">
          <span className="stat-label">当前需处理</span>
          <ShieldAlert size={18} />
        </div>
        <div className="stat-value">{totals.active_alerts}</div>
        <div className="stat-sub">
          <span>条活跃告警</span>
          <button type="button" className="inline-action" onClick={onFocusAlerts}>
            查看清单 <ArrowRight size={12} />
          </button>
        </div>
        <div className="attention-metrics">
          <MiniMetric label="停滞" value={totals.stalled} tone="warn" />
          <MiniMetric label="超时" value={totals.overdue} tone="danger" />
        </div>
      </article>

      <article className="stat-card">
        <div className="stat-topline">
          <span className="stat-label">在途包裹</span>
          <PackageOpen size={17} />
        </div>
        <div className="stat-value">{totals.open}</div>
        <div className="stat-sub">未到终点的包裹</div>
        <div className="stat-foot">
          <span className="neutral-dot" /> 含停滞与正常在途
        </div>
      </article>

      <button type="button" className="stat-card stat-button" onClick={() => onFilterAlert("STALLED")}>
        <div className="stat-topline">
          <span className="stat-label">停滞告警</span>
          <PauseCircle size={17} />
        </div>
        <div className="stat-value warn-ink">{totals.stalled}</div>
        <div className="stat-sub">连续 4 工作小时无进展</div>
        <div className="stat-foot warn-foot">
          <TriangleAlert size={13} /> 点击筛出停滞件
        </div>
      </button>

      <button type="button" className="stat-card stat-button" onClick={() => onFilterAlert("OVERALL_TIMEOUT")}>
        <div className="stat-topline">
          <span className="stat-label">整体超时</span>
          <Clock3 size={17} />
        </div>
        <div className="stat-value danger-ink">{totals.overdue}</div>
        <div className="stat-sub">揽收到签收超 24 工作小时</div>
        <div className="stat-foot danger-foot">
          <CircleAlert size={13} /> 点击筛出超时件
        </div>
      </button>

      <article className="stat-card">
        <div className="stat-topline">
          <span className="stat-label">异常扫描</span>
          <ScanSearch size={17} />
        </div>
        <div className="stat-value">{totals.anomalies}</div>
        <div className="stat-sub">未知状态 / 不合理倒退</div>
        <div className="stat-foot">
          <span className="badge-mini">{totals.late_scans} 条晚到</span>
          <span>接收时间不参与排序</span>
        </div>
      </article>

      <article className="stat-card stat-outcomes">
        <div className="stat-topline">
          <span className="stat-label">已完成结果</span>
          <Sparkles size={17} />
        </div>
        <div className="outcome-row">
          <span>
            <b>{totals.delivered}</b>
            签收
          </span>
          <span>
            <b>{totals.returned}</b>
            退回
          </span>
          <span>
            <b>{totals.cancelled}</b>
            取消
          </span>
        </div>
        <div className="stat-sub">退回与取消单独统计</div>
        <div className="stat-foot">
          <span className="neutral-dot" /> 共 {totals.packages} 个包裹
        </div>
      </article>
    </section>
  );
}
