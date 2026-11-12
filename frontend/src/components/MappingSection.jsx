import React from "react";
import {
  ArrowRight,
  CalendarOff,
  CircleHelp,
  Clock3,
  TimerReset,
  TriangleAlert,
  Workflow,
} from "lucide-react";
import { StatusPill } from "./Shared";
import { datePart } from "../utils";

export function MappingSection({ mappings, holidays = [], thresholds }) {
  const canonical = mappings?.canonical || [];
  const carriers = mappings?.carriers || [];
  const unmapped = mappings?.unmapped || [];

  return (
    <section className="mapping-section" id="mapping">
      <div className="section-heading">
        <div>
          <span className="eyebrow">CARRIER DICTIONARY</span>
          <h2>承运商状态映射</h2>
          <p>
            不同承运商的原始扫描代码，统一映射为揽收、运输、到站、派送、签收、退回、取消。
            未知代码只进入异常清单，不推进包裹进度。
          </p>
        </div>
        <div className="canonical-legend">
          {canonical
            .filter((status) => status.code !== "PENDING")
            .map((status) => (
              <StatusPill
                key={status.code}
                status={status.code}
                label={status.label}
                catalog={canonical}
                compact
              />
            ))}
        </div>
      </div>

      <div className="rule-strip" id="rules">
        <div className="rule-item">
          <span className="rule-icon">
            <Clock3 size={16} />
          </span>
          <div>
            <strong>{thresholds?.work_window || "09:00–18:00"}</strong>
            <span>北京时间工作窗口</span>
          </div>
        </div>
        <div className="rule-item">
          <span className="rule-icon warn">
            <TimerReset size={16} />
          </span>
          <div>
            <strong>4 工作小时</strong>
            <span>无有效进展即停滞</span>
          </div>
        </div>
        <div className="rule-item">
          <span className="rule-icon danger">
            <Clock3 size={16} />
          </span>
          <div>
            <strong>24 工作小时</strong>
            <span>揽收到签收整体超时</span>
          </div>
        </div>
        <div className="rule-item">
          <span className="rule-icon aqua">
            <CalendarOff size={16} />
          </span>
          <div>
            <strong>跳过周末与节假日</strong>
            <span>导入假日不累计时长</span>
          </div>
        </div>
      </div>

      <div className="mapping-grid">
        {carriers.map((carrier) => (
          <article className="mapping-card" key={carrier.code}>
            <header>
              <span className="carrier-monogram">{carrier.code}</span>
              <div>
                <strong>{carrier.name}</strong>
                <small>{carrier.mappings.length} 个状态代码</small>
              </div>
              <Workflow size={16} />
            </header>
            <div className="mapping-rows">
              {carrier.mappings.map((row) => (
                <div className="mapping-row" key={row.raw_code}>
                  <span className="raw-code">
                    {row.raw_code}
                    <small>{row.raw_label}</small>
                  </span>
                  <ArrowRight size={13} />
                  <StatusPill status={row.canonical_status} label={row.canonical_label} compact />
                </div>
              ))}
            </div>
          </article>
        ))}
      </div>

      <div className="mapping-bottom">
        <div className="unmapped-card">
          <span className="unmapped-icon">
            <CircleHelp size={19} />
          </span>
          <div>
            <strong>未映射代码演示</strong>
            {unmapped.length ? (
              <div className="unmapped-items">
                {unmapped.map((item) => (
                  <span className="unmapped-item" key={`${item.carrier}-${item.raw_code}`}>
                    <b>{item.raw_code}</b>
                    <small>{item.carrier} · {item.raw_label}</small>
                    <em>不推进</em>
                  </span>
                ))}
              </div>
            ) : (
              <p>当前没有未知状态代码。</p>
            )}
          </div>
        </div>

        <div className="holiday-card">
          <span className="holiday-icon">
            <CalendarOff size={19} />
          </span>
          <div>
            <strong>已导入节假日</strong>
            <div className="holiday-chips">
              {holidays.length ? (
                holidays.map((holiday) => (
                  <span className="holiday-chip" key={holiday.date}>
                    {datePart(`${holiday.date}T00:00:00+08:00`)}
                    <small>{holiday.name}</small>
                  </span>
                ))
              ) : (
                <span>尚未导入</span>
              )}
            </div>
            <p>这些日期只跳过计时，扫描仍按发生时间进入轨迹。</p>
          </div>
        </div>
      </div>

      {unmapped.length ? (
        <div className="mapping-warn">
          <TriangleAlert size={14} />
          {unmapped.length} 个扫描代码未在字典中：展示为「未映射」，列为异常，不改变当前状态。
        </div>
      ) : null}
    </section>
  );
}
