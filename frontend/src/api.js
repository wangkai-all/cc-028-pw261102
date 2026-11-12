const API_BASE = import.meta.env.VITE_API_BASE || "/api";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      /* ignore */
    }
    throw new Error(message);
  }
  return response.json();
}

const withAsOf = (path, asOf) => {
  if (!asOf) return path;
  const joiner = path.includes("?") ? "&" : "?";
  return `${path}${joiner}as_of=${encodeURIComponent(asOf)}`;
};

export function getOverview(asOf) {
  return request(withAsOf("/overview", asOf));
}

export function getPackages(asOf, filters = {}) {
  const params = new URLSearchParams();
  if (asOf) params.set("as_of", asOf);
  if (filters.q) params.set("q", filters.q);
  if (filters.carrier) params.set("carrier", filters.carrier);
  if (filters.status) params.set("status", filters.status);
  if (filters.alertOnly) params.set("alert_only", "true");
  if (filters.alertType) params.set("alert_type", filters.alertType);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request(`/packages${suffix}`);
}

export function getPackage(trackingNo, asOf) {
  return request(withAsOf(`/packages/${encodeURIComponent(trackingNo)}`, asOf));
}

export function getMappings() {
  return request("/mappings");
}

export function getImports() {
  return request("/imports");
}

export function getHolidays() {
  return request("/holidays");
}

export function importScans(payload) {
  return request("/scans/import", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function importHolidays(payload) {
  return request("/holidays/import", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function recalculate(asOf) {
  return request("/recalculate", {
    method: "POST",
    body: JSON.stringify({ as_of: asOf || null }),
  });
}

export function getSupplementSample(trackingNo) {
  const suffix = trackingNo ? `?tracking_no=${encodeURIComponent(trackingNo)}` : "";
  return request(`/demo/supplement${suffix}`);
}

export function supplementPackage(trackingNo) {
  return request(`/packages/${encodeURIComponent(trackingNo)}/supplement`, {
    method: "POST",
  });
}

export function resetDemo() {
  return request("/demo/reset", { method: "POST" });
}
