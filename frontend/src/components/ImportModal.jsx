import React, { useEffect, useMemo, useState } from "react";
import {
  CalendarOff,
  CheckCircle2,
  Clock3,
  Copy,
  Database,
  FileJson,
  Info,
  RefreshCw,
  RotateCcw,
  Upload,
  X,
} from "lucide-react";
import {
  getHolidays,
  getImports,
  getSupplementSample,
  importHolidays,
  importScans,
  resetDemo,
} from "../api";
import { dateTimePart, hours } from "../utils";
import { Spinner } from "./Shared";

function TabButton({ active, onClick, icon, children }) {
  return (
    <button type="button" className={`tab-button ${active ? "active" : ""}`} onClick={onClick}>
      {icon}
      {children}
    </button>
  );
}

export function ImportModal({ open, onClose, onRefresh, addToast, carriers }) {
  const [tab, setTab] = useState("scans");
  const [source, setSource] = useState("手动导入");
  const [carrier, setCarrier] = useState("SF");
  const [recordsText, setRecordsText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [batches, setBatches] = useState([]);
  const [holidays, setHolidays] = useState([]);
  const [holidayName, setHolidayName] = useState("公司假日");
  const [holidayText, setHolidayText] = useState("");
  const [sample, setSample] = useState(null);
  const [batchLoading, setBatchLoading] = useState(false);

  const sampleText = useMemo(() => {
    if (!sample?.record) return "";
    return JSON.stringify([sample.record], null, 2);
  }, [sample]);

  useEffect(() => {
    if (!open) return;
    setError("");
    setResult(null);
    setBatchLoading(true);
    Promise.all([getImports(), getHolidays(), getSupplementSample()])
      .then(([importsResponse, holidayResponse, sampleResponse]) => {
        setBatches(importsResponse.items || []);
        setHolidays(holidayResponse.items || []);
        setSample(sampleResponse);
        if (sampleResponse?.record) {
          setRecordsText(JSON.stringify([sampleResponse.record], null, 2));
          setCarrier(sampleResponse.carrier || "SF");
          setSource("补录缺失扫描");
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => setBatchLoading(false));
  }, [open]);

  useEffect(() => {
    const handler = (event) => {
      if (event.key === "Escape" && open) onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  async function refreshReferenceData() {
    const [importsResponse, holidayResponse] = await Promise.all([getImports(), getHolidays()]);
    setBatches(importsResponse.items || []);
    setHolidays(holidayResponse.items || []);
  }

  async function submitScans(event) {
    event.preventDefault();
    setError("");
    setResult(null);
    let parsed;
    try {
      parsed = JSON.parse(recordsText);
    } catch {
      setError("JSON 格式不正确，请检查逗号、引号和括号。");
      return;
    }
    const records = Array.isArray(parsed) ? parsed : parsed.records;
    if (!Array.isArray(records) || records.length === 0) {
      setError("请提供至少一条扫描记录（JSON 数组或包含 records 的对象）。");
      return;
    }
    setBusy(true);
    try {
      const response = await importScans({
        source: source || "手动导入",
        carrier: carrier || null,
        records,
        recalculate: true,
      });
      setResult(response);
      await refreshReferenceData();
      await onRefresh();
      addToast(
        `导入完成：新增 ${response.import.inserted_count} 条，去重 ${response.import.duplicate_count} 条，已重算告警。`,
      );
      const newSample = await getSupplementSample().catch(() => null);
      setSample(newSample);
    } catch (err) {
      setError(err.message);
      addToast(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function submitHolidays(event) {
    event.preventDefault();
    setError("");
    setResult(null);
    const dates = holidayText
      .split(/[\s,，;；]+/)
      .map((value) => value.trim())
      .filter(Boolean);
    if (!dates.length) {
      setError("请至少输入一个日期，例如 2026-11-18。");
      return;
    }
    setBusy(true);
    try {
      const response = await importHolidays({
        dates,
        name: holidayName || "导入节假日",
        recalculate: true,
      });
      setResult({ holidays: response, kind: "holiday" });
      await refreshReferenceData();
      await onRefresh();
      addToast(`已导入 ${response.inserted} 个节假日，并重新计算告警。`);
    } catch (err) {
      setError(err.message);
      addToast(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function handleReset() {
    if (!window.confirm("恢复演示数据会清空当前导入、补录和告警历史，确定继续吗？")) return;
    setBusy(true);
    setError("");
    try {
      await resetDemo();
      await refreshReferenceData();
      await onRefresh();
      setResult({ reset: true });
      addToast("演示数据已恢复。");
      const newSample = await getSupplementSample().catch(() => null);
      setSample(newSample);
    } catch (err) {
      setError(err.message);
      addToast(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div className="modal-layer" role="presentation">
      <div className="modal-backdrop" onClick={onClose} />
      <div className="import-modal" role="dialog" aria-modal="true" aria-label="数据导入">
        <div className="modal-header">
          <div>
            <span className="eyebrow">DATA PIPELINE</span>
            <h2>数据导入与重算</h2>
            <p>导入承运商扫描或节假日；导入后自动重算当前告警并保留变化历史。</p>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="关闭导入">
            <X size={18} />
          </button>
        </div>

        <div className="modal-tabs">
          <TabButton active={tab === "scans"} onClick={() => setTab("scans")} icon={<FileJson size={15} />}>
            扫描记录
          </TabButton>
          <TabButton active={tab === "holidays"} onClick={() => setTab("holidays")} icon={<CalendarOff size={15} />}>
            节假日
          </TabButton>
          <TabButton active={tab === "batches"} onClick={() => setTab("batches")} icon={<Database size={15} />}>
            导入批次
          </TabButton>
        </div>

        {error ? <div className="modal-error">{error}</div> : null}

        {tab === "scans" ? (
          <form className="import-form" onSubmit={submitScans}>
            <div className="import-context">
              <Info size={14} />
              <span>
                轨迹按 <b>发生时间</b> 排序，<b>接收时间</b> 只记录数据何时到达。相同扫描编号会自动去重。
              </span>
            </div>
            <div className="form-row">
              <label>
                来源名称
                <input value={source} onChange={(event) => setSource(event.target.value)} placeholder="例如：顺丰 TMS 回传" />
              </label>
              <label>
                默认承运商
                <select value={carrier} onChange={(event) => setCarrier(event.target.value)}>
                  {carriers.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.code} · {item.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="json-field">
              <span className="json-label">
                扫描记录 JSON
                <button
                  type="button"
                  className="text-button with-icon"
                  onClick={() => {
                    if (sampleText) {
                      setRecordsText(sampleText);
                      setCarrier(sample.carrier || "SF");
                      setSource("补录缺失扫描");
                    }
                  }}
                  disabled={!sampleText}
                >
                  <RefreshCw size={12} /> 载入补录样例
                </button>
              </span>
              <textarea
                value={recordsText}
                onChange={(event) => setRecordsText(event.target.value)}
                rows={10}
                spellCheck="false"
                placeholder={'[{"tracking_no":"...","scan_id":"...","carrier":"SF","status_code":"SF_PICKUP","occurred_at":"2026-11-12T09:00:00+08:00","received_at":"..."}]'}
              />
            </label>
            {sample ? (
              <div className="sample-note">
                <Clock3 size={13} />
                {sample.explanation}
              </div>
            ) : null}
            <div className="modal-actions">
              <span className="modal-hint">未知状态代码会入库并列为异常，但不推进进度。</span>
              <button type="submit" className="primary-button" disabled={busy}>
                {busy ? <Spinner label="导入中" /> : <><Upload size={15} /> 导入并重算</>}
              </button>
            </div>
          </form>
        ) : null}

        {tab === "holidays" ? (
          <form className="import-form" onSubmit={submitHolidays}>
            <div className="import-context">
              <Info size={14} />
              <span>
                导入节假日只影响工作时段累计，不会删除或隐藏扫描；历史告警会按新日历重算。
              </span>
            </div>
            <div className="form-row">
              <label>
                节假日名称
                <input
                  value={holidayName}
                  onChange={(event) => setHolidayName(event.target.value)}
                  placeholder="例如：公司假日"
                />
              </label>
            </div>
            <label className="json-field">
              日期列表
              <textarea
                value={holidayText}
                onChange={(event) => setHolidayText(event.target.value)}
                rows={5}
                placeholder={"2026-11-18\n2026-11-19\n也支持用逗号分隔"}
              />
            </label>
            <div className="holiday-summary">
              <span>已导入 {holidays.length} 天</span>
              {holidays.slice(0, 12).map((holiday) => (
                <span className="holiday-chip" key={holiday.date}>
                  {holiday.date.slice(5)}
                  <small>{holiday.name}</small>
                </span>
              ))}
            </div>
            <div className="modal-actions">
              <span className="modal-hint">周末无需导入，系统始终跳过。</span>
              <button type="submit" className="primary-button" disabled={busy}>
                {busy ? <Spinner label="导入中" /> : <><CalendarOff size={15} /> 导入节假日并重算</>}
              </button>
            </div>
          </form>
        ) : null}

        {tab === "batches" ? (
          <div className="batch-panel">
            {batchLoading ? <Spinner label="读取批次…" /> : null}
            <div className="batch-list">
              {batches.map((batch) => (
                <div className="batch-row" key={batch.id}>
                  <span className="batch-id">#{batch.id}</span>
                  <div>
                    <strong>{batch.source}</strong>
                    <small>
                      {dateTimePart(batch.imported_at)} · {batch.carrier || "多承运商"}
                    </small>
                  </div>
                  <span className="batch-count good">
                    <b>{batch.inserted_count}</b> 新增
                  </span>
                  <span className="batch-count">
                    <Copy size={12} />
                    <b>{batch.duplicate_count}</b> 去重
                  </span>
                  <span className={`batch-count ${batch.rejected_count ? "bad" : ""}`}>
                    <b>{batch.rejected_count}</b> 拒绝
                  </span>
                </div>
              ))}
            </div>
            {!batchLoading && !batches.length ? (
              <div className="batch-empty">还没有导入批次。</div>
            ) : null}
            <div className="batch-note">
              <Info size={13} />
              重复导入演练批次会显示新增 0、去重 N，原有扫描不会被覆盖。
            </div>
          </div>
        ) : null}

        {result?.import ? (
          <div className="import-result">
            <CheckCircle2 size={18} />
            <div>
              <strong>批次 #{result.import.batch_id} 已写入</strong>
              <span>
                接收 {result.import.received_count} · 新增 {result.import.inserted_count} · 去重{" "}
                {result.import.duplicate_count} · 拒绝 {result.import.rejected_count}
                {result.import.unknown_status_count
                  ? ` · 未知状态 ${result.import.unknown_status_count}`
                  : ""}
              </span>
            </div>
            <span className="result-note">告警已重算</span>
          </div>
        ) : null}
        {result?.holidays ? (
          <div className="import-result">
            <CheckCircle2 size={18} />
            <div>
              <strong>节假日已写入</strong>
              <span>{result.holidays.inserted} 个日期，告警已重算</span>
            </div>
          </div>
        ) : null}
        {result?.reset ? (
          <div className="import-result">
            <CheckCircle2 size={18} />
            <div>
              <strong>演示数据已恢复</strong>
              <span>扫描、批次、节假日与告警历史回到初始状态</span>
            </div>
          </div>
        ) : null}

        <div className="modal-footer">
          <div>
            <span>演示环境</span>
            <button type="button" className="danger-text-button" onClick={handleReset} disabled={busy}>
              <RotateCcw size={13} /> 恢复演示数据
            </button>
          </div>
          <div className="modal-foot-meta">
            <Clock3 size={13} />
            北京时间 · 09:00–18:00 计时 · 周末及节假日跳过
          </div>
        </div>
      </div>
    </div>
  );
}
