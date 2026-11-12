import React from "react";
import {
  CalendarClock,
  Database,
  Moon,
  RefreshCw,
  ScanLine,
  Sun,
  Upload,
} from "lucide-react";

export function Header({
  observationDraft,
  onObservationDraft,
  onApplyObservation,
  onNow,
  onRecalculate,
  onOpenImport,
  theme,
  onToggleTheme,
  recalculating,
  workClock,
}) {
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <a className="brand" href="#monitor" aria-label="轨迹哨站首页">
          <span className="brand-mark">
            <ScanLine size={21} />
          </span>
          <span className="brand-text">
            <strong>轨迹哨站</strong>
            <small>TRACE CONSOLE</small>
          </span>
        </a>

        <nav className="topnav" aria-label="页面导航">
          <a href="#monitor">监控台</a>
          <a href="#mapping">状态映射</a>
          <a href="#rules">计时规则</a>
        </nav>

        <div className="topbar-actions">
          <div className="work-state">
            <span className={`live-dot ${workClock?.is_counting ? "counting" : "resting"}`} />
            <span>
              北京时间 · 周{workClock?.weekday || "?"}
              <small>
                {workClock?.is_counting
                  ? "工作计时中"
                  : workClock?.skip_reason
                    ? `${workClock.skip_reason}不计时`
                    : "非工作时段"}
              </small>
            </span>
          </div>

          <div className="observation-control">
            <CalendarClock size={15} aria-hidden="true" />
            <label htmlFor="observation-time">观察时刻</label>
            <input
              id="observation-time"
              type="datetime-local"
              value={observationDraft}
              onChange={(event) => onObservationDraft(event.target.value)}
              aria-label="指定观察时刻"
            />
            <button type="button" className="ghost-button compact" onClick={onApplyObservation}>
              应用
            </button>
            <button type="button" className="text-button" onClick={onNow}>
              现在
            </button>
          </div>

          <div className="topbar-buttons">
            <button
              type="button"
              className="icon-button"
              onClick={onToggleTheme}
              aria-label={theme === "dark" ? "切换到浅色模式" : "切换到深色模式"}
              title={theme === "dark" ? "浅色模式" : "深色模式"}
            >
              {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={onRecalculate}
              disabled={recalculating}
            >
              <RefreshCw size={15} className={recalculating ? "spin" : ""} />
              {recalculating ? "重算中" : "重算告警"}
            </button>
            <button type="button" className="primary-button" onClick={onOpenImport}>
              <Upload size={15} />
              导入数据
            </button>
          </div>
        </div>
      </div>
      <div className="topbar-mobile-observation">
        <Database size={13} />
        数据与时间判断均在服务端完成
      </div>
    </header>
  );
}
