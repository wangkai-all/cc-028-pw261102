import React from "react";
import {
  CalendarDays,
  Clock3,
  GitBranch,
  History,
  Radar,
  TimerReset,
} from "lucide-react";
import { datePart, fullDate, timePart } from "../utils";

function WorkWindowMeter({ workClock }) {
  // workClock.now 是带 +08:00 的北京时间字符串；直接取墙钟小时分钟，
  // 避免 new Date().getHours() 随查看者本机时区变化。
  const match = workClock?.now?.match(/T(\d{2}):(\d{2})/);
  const minutes = match ? Number(match[1]) * 60 + Number(match[2]) : 9 * 60;
  const ratio = Math.min(1, Math.max(0, (minutes - 9 * 60) / (9 * 60)));
  return (
    <div className={`work-window-meter ${workClock?.is_counting ? "counting" : "resting"}`}>
      <div className="meter-track" aria-hidden="true">
        <span className="meter-fill" style={{ width: `${ratio * 100}%` }} />
        <span className="meter-marker" style={{ left: `${ratio * 100}%` }} />
      </div>
      <div className="meter-labels">
        <span>09:00</span>
        <span>12:00</span>
        <span>18:00</span>
      </div>
    </div>
  );
}

export function Hero({ overview }) {
  const workClock = overview?.work_clock;
  return (
    <section className="hero" aria-label="系统说明">
      <div className="hero-copy">
        <div className="hero-badge">
          <Radar size={14} />
          按发生时间还原，而不是按接收时间排序
        </div>
        <h1>
          包裹停在哪一步，
          <br />
          从轨迹里看得出来。
        </h1>
        <p>
          导入不同承运商的扫描记录，统一映射物流状态；只累计北京工作日
          09:00–18:00 的时间，把停滞、整体超时、晚到补录和异常回退分开处理。
        </p>
        <div className="hero-principles">
          <span>
            <History size={14} />
            晚到扫描补进历史
          </span>
          <span>
            <GitBranch size={14} />
            异常扫描不推进
          </span>
          <span>
            <TimerReset size={14} />
            同告警只保留当前一条
          </span>
        </div>
      </div>

      <aside className="hero-clock-card" aria-label="当前北京时间与工作时段">
        <div className="hero-clock-top">
          <span className={`clock-state ${workClock?.is_counting ? "on" : "off"}`}>
            <span className="live-dot" />
            {workClock?.is_counting ? "工作时段计时中" : workClock?.skip_reason || "非工作时段"}
          </span>
          <Clock3 size={17} />
        </div>
        <div className="hero-time">
          <strong>{workClock?.now ? timePart(workClock.now) : "--:--"}</strong>
          <div>
            <small>北京时间</small>
            <span>周{workClock?.weekday || "-"}</span>
          </div>
        </div>
        <WorkWindowMeter workClock={workClock} />
        <div className="hero-clock-meta">
          <span>
            <CalendarDays size={13} />
            {workClock?.now ? fullDate(workClock.now) : "—"}
          </span>
          <span>已导入 {overview?.holidays?.length || 0} 天节假日</span>
        </div>
        <div className="hero-snapshot">
          <span>观察快照</span>
          <strong>
            {overview ? `${datePart(overview.as_of)} ${timePart(overview.as_of)}` : "—"}
          </strong>
          <small>之后发生的扫描不参与判断</small>
        </div>
      </aside>
    </section>
  );
}
