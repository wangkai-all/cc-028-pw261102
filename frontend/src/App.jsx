import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import {
  getMappings,
  getOverview,
  getPackage,
  getPackages,
  recalculate,
  supplementPackage,
} from "./api";
import { Header } from "./components/Header";
import { Hero } from "./components/Hero";
import { StatCards } from "./components/StatCards";
import { PackageTable } from "./components/PackageTable";
import { AlertRail } from "./components/AlertRail";
import { MappingSection } from "./components/MappingSection";
import { PackageDrawer } from "./components/PackageDrawer";
import { ImportModal } from "./components/ImportModal";
import { Toast } from "./components/Shared";
import { localObservation, toObservationIso } from "./utils";

const INITIAL_FILTERS = {
  q: "",
  carrier: "",
  status: "",
  alertOnly: false,
  alertType: null,
};

export default function App() {
  const [theme, setTheme] = useState(() => {
    const saved = window.localStorage.getItem("tracker-theme");
    if (saved) return saved;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });
  const [overview, setOverview] = useState(null);
  const [packages, setPackages] = useState([]);
  const [mappings, setMappings] = useState(null);
  const [asOf, setAsOf] = useState("");
  const [observationDraft, setObservationDraft] = useState("");
  const [filters, setFilters] = useState(INITIAL_FILTERS);
  const [packagesLoading, setPackagesLoading] = useState(false);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [pageError, setPageError] = useState("");
  const [recalculating, setRecalculating] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [selectedTrackingNo, setSelectedTrackingNo] = useState("");
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [supplementing, setSupplementing] = useState("");
  const [toast, setToast] = useState(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const toastTimer = useRef(null);

  const statusCatalog = useMemo(() => overview?.status_catalog || [], [overview]);
  const carriers = useMemo(() => mappings?.carriers || [], [mappings]);

  const addToast = useCallback((message, type = "success") => {
    window.clearTimeout(toastTimer.current);
    setToast({ message, type });
    toastTimer.current = window.setTimeout(() => setToast(null), 4200);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("tracker-theme", theme);
  }, [theme]);

  const loadOverview = useCallback(async (requestedAsOf = null) => {
    setOverviewLoading(true);
    setPageError("");
    try {
      const response = await getOverview(requestedAsOf);
      setOverview(response);
      setAsOf(response.as_of);
      setObservationDraft(localObservation(response.as_of));
      setRefreshTick((value) => value + 1);
      return response;
    } catch (error) {
      setPageError(error.message);
      addToast(error.message, "error");
      return null;
    } finally {
      setOverviewLoading(false);
    }
  }, [addToast]);

  useEffect(() => {
    getMappings().then(setMappings).catch((error) => addToast(error.message, "error"));
    loadOverview(null);
  }, [loadOverview, addToast]);

  useEffect(() => {
    if (!asOf) return undefined;
    let active = true;
    const timer = window.setTimeout(async () => {
      setPackagesLoading(true);
      try {
        const response = await getPackages(asOf, filters);
        if (active) setPackages(response.items || []);
      } catch (error) {
        if (active) {
          setPageError(error.message);
          addToast(error.message, "error");
        }
      } finally {
        if (active) setPackagesLoading(false);
      }
    }, 180);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [asOf, filters, refreshTick, addToast]);

  const loadDetail = useCallback(async (trackingNo, observedAt) => {
    if (!trackingNo || !observedAt) return;
    setDetailLoading(true);
    try {
      const response = await getPackage(trackingNo, observedAt);
      setDetail(response);
    } catch (error) {
      addToast(error.message, "error");
    } finally {
      setDetailLoading(false);
    }
  }, [addToast]);

  useEffect(() => {
    if (selectedTrackingNo && asOf) loadDetail(selectedTrackingNo, asOf);
  }, [selectedTrackingNo, asOf, refreshTick, loadDetail]);

  async function handleApplyObservation() {
    const value = toObservationIso(observationDraft);
    if (!value) {
      addToast("请选择观察时刻", "error");
      return;
    }
    const response = await loadOverview(value);
    if (response) addToast(`已切换到观察时刻 ${value.slice(0, 16).replace("T", " ")}`);
  }

  async function handleNow() {
    const response = await loadOverview(null);
    if (response) addToast("已回到当前北京时间。");
  }

  async function handleRecalculate() {
    setRecalculating(true);
    try {
      const result = await recalculate(asOf);
      await loadOverview(asOf);
      addToast(
        `重算完成：活跃告警 ${result.active_alerts} 条，新增 ${result.created}，更新 ${result.updated}，解除 ${result.cleared}。`,
      );
    } catch (error) {
      addToast(error.message, "error");
    } finally {
      setRecalculating(false);
    }
  }

  function focusAlert(type) {
    setFilters((current) => ({
      ...current,
      alertOnly: true,
      alertType: type,
    }));
    window.setTimeout(() => {
      document.getElementById("monitor")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 0);
  }

  function focusAlertRail() {
    document.getElementById("alert-rail")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function handleSupplement(trackingNo) {
    const target = trackingNo || selectedTrackingNo;
    if (!target) {
      addToast("未找到需要补录的包裹", "error");
      return;
    }
    setSupplementing(target);
    try {
      const result = await supplementPackage(target);
      await loadOverview(asOf);
      await loadDetail(target, asOf);
      addToast(
        `已补录 ${result.import.inserted_count} 条扫描并重新计算：新增告警 ${result.recalculated.created}，解除 ${result.recalculated.cleared}。`,
      );
    } catch (error) {
      addToast(error.message, "error");
    } finally {
      setSupplementing("");
    }
  }

  function openPackage(trackingNo) {
    setSelectedTrackingNo(trackingNo);
    setDetail(null);
  }

  function closePackage() {
    setSelectedTrackingNo("");
    setDetail(null);
  }

  const activeAlerts = overview?.active_alerts || [];

  return (
    <div className="app-shell" data-loading={overviewLoading ? "true" : "false"}>
      <Header
        observationDraft={observationDraft}
        onObservationDraft={setObservationDraft}
        onApplyObservation={handleApplyObservation}
        onNow={handleNow}
        onRecalculate={handleRecalculate}
        onOpenImport={() => setImportOpen(true)}
        theme={theme}
        onToggleTheme={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
        recalculating={recalculating}
        workClock={overview?.work_clock}
      />

      <main className="page">
        {pageError ? (
          <div className="error-banner" role="alert">
            <AlertTriangle size={16} />
            <span>{pageError}</span>
            <button type="button" onClick={() => loadOverview(asOf || null)}>
              <RefreshCw size={13} /> 重试
            </button>
          </div>
        ) : null}

        <Hero overview={overview} />

        {overview ? (
          <StatCards
            overview={overview}
            onFocusAlerts={focusAlertRail}
            onFilterAlert={focusAlert}
          />
        ) : (
          <div className="skeleton-grid" aria-hidden="true">
            {Array.from({ length: 6 }).map((_, index) => <span key={index} />)}
          </div>
        )}

        <div className="dashboard-grid">
          <PackageTable
            items={packages}
            filters={filters}
            onFilterChange={setFilters}
            carriers={carriers}
            statusCatalog={statusCatalog}
            onSelect={openPackage}
            loading={packagesLoading}
            total={packages.length}
          />
          <AlertRail
            alerts={activeAlerts}
            asOf={asOf}
            onSelect={openPackage}
            onSupplement={handleSupplement}
            supplementing={supplementing}
          />
        </div>

        {mappings && overview ? (
          <MappingSection
            mappings={mappings}
            holidays={overview.holidays}
            thresholds={{
              ...overview.thresholds,
              work_window: overview.thresholds.work_window,
            }}
          />
        ) : (
          <div className="skeleton-panel" aria-hidden="true" />
        )}
      </main>

      <footer className="app-footer">
        <span>演示数据覆盖跨周末、国庆长假、晚到扫描、重复导入与异常回退。</span>
        <span>React · FastAPI · DuckDB · 北京时间 UTC+8</span>
      </footer>

      {selectedTrackingNo ? (
        <PackageDrawer
          detail={detail}
          loading={detailLoading}
          onClose={closePackage}
          onSupplement={handleSupplement}
          supplementing={Boolean(supplementing)}
          statusCatalog={statusCatalog}
        />
      ) : null}

      <ImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onRefresh={() => loadOverview(asOf)}
        addToast={addToast}
        carriers={carriers}
      />

      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
