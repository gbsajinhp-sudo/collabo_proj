import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource, LngLatBoundsLike, MapLayerMouseEvent } from "maplibre-gl";
import type { Feature, FeatureCollection, Geometry, MultiPolygon, Point, Polygon } from "geojson";
import "maplibre-gl/dist/maplibre-gl.css";
import "./styles.css";

type Metric = "density" | "lq" | "growth";
type IndustryLevel = "all" | "major" | "middle" | "minor" | "detail";
type SelectableLevel = Exclude<IndustryLevel, "all">;
type LayerMode = "heat" | "points";
type BasemapMode = "data" | "osm";
type DimensionItem = {
  industry_level?: SelectableLevel; industry_key?: string; industry_name?: string; parent_key?: string;
  major_key?: string; middle_key?: string; minor_key?: string; detail_key?: string;
  major_name?: string; middle_name?: string; minor_name?: string;
  region_code?: string; region_name?: string;
};
type DashboardMeta = { analysis_years: number[]; boundary: { version: string }; classification: { growth_break_years: number[] } };
type Summary = { record_count: number; address_count: number; address_count_method: string; growth_rate: number | null };
type TrendItem = { year: number; record_count: number; address_count: number };
type ApiFeatureCollection = FeatureCollection<Geometry, Record<string, unknown>> & { meta: Record<string, unknown> };

const levels: SelectableLevel[] = ["major", "middle", "minor", "detail"];
const levelLabels: Record<SelectableLevel, string> = { major: "대분류", middle: "중분류", minor: "소분류", detail: "세세분류" };
const nextLevel: Partial<Record<SelectableLevel, SelectableLevel>> = { major: "middle", middle: "minor", minor: "detail" };
const emptyCollection: FeatureCollection = { type: "FeatureCollection", features: [] };
const numberFormat = new Intl.NumberFormat("ko-KR");
const percentFormat = new Intl.NumberFormat("ko-KR", { style: "percent", maximumFractionDigits: 1, signDisplay: "exceptZero" });
const app = document.querySelector<HTMLDivElement>("#app");
if (!app) throw new Error("Application root was not found.");

app.innerHTML = `
  <main class="dashboard-shell">
    <header class="topbar">
      <div class="title-ci"><img src="/gbsa-ci.png" alt="경기도경제과학진흥원"><span>&copy; 2026 sangb.park, All rights reserved.</span></div>
      <div class="page-title"><h1>경기도 산업집적 탐색기</h1></div>
      <div class="topbar-meta"><span id="api-status" class="live-dot">데이터 연결 중</span><span class="boundary-date">행정경계 2025.12.31</span></div>
    </header>
    <section class="workspace">
      <aside class="control-panel" aria-label="분석 조건">
        <div class="control-content">
          <div class="panel-heading"><div><span>01</span><p>분석 조건</p></div><button id="reset-filter" class="text-button" type="button">초기화</button></div>
          <section class="filter-block"><label>조사연도</label><div id="year-tabs" class="year-tabs"></div><p class="field-note">2019~2023년 10차, 2024년 11차 산업분류 적용</p></section>
          <section class="filter-block industry-filter">
            <label for="industry-global-search">산업분류 다중선택</label>
            <div class="global-search-wrap">
              <input id="industry-global-search" type="search" placeholder="업종명 검색 (예: 반도체)" autocomplete="off">
              <div id="industry-search-results" class="search-results" hidden></div>
            </div>
            <p class="field-note hierarchy-note">각 단계에서 복수 선택할 수 있습니다. 선택이 없으면 해당 단계는 전체입니다.</p>
            <div id="industry-selectors" class="industry-selectors"></div>
            <div id="industry-path" class="selection-path">전체 산업</div>
          </section>
          <section class="filter-block">
            <label for="sigun-select">지도 지역</label>
            <select id="sigun-select"><option value="">경기도 전체</option></select>
            <select id="emd-select" disabled><option value="">행정동 전체</option></select>
            <p class="field-note">주소는 조사 당시 값을 보존하고 지도 경계만 2025.12.31 기준 사용</p>
          </section>
          <section class="metric-block">
            <label>히트맵 지표</label>
            <div class="metric-tabs" role="group" aria-label="히트맵 지표">
              <button class="metric-button active" data-metric="density" type="button"><b>집적도</b><small>사업체 / ㎢</small></button>
              <button class="metric-button" data-metric="lq" type="button"><b>특화도</b><small>경기도 대비 LQ</small></button>
              <button class="metric-button" data-metric="growth" type="button"><b>증감률</b><small>전년 대비</small></button>
            </div>
            <div id="metric-help" class="metric-help">사업체가 밀집된 절대적 중심지를 보여줍니다.</div>
          </section>
        </div>
      </aside>
      <section class="map-stage" aria-label="산업집적 지도">
        <div id="map"></div><canvas id="map-overlay" aria-hidden="true"></canvas>
        <div class="map-tools">
          <div class="map-switches">
            <div class="layer-switch" role="group" aria-label="지도 표현 방식"><button class="active" data-layer="heat" type="button">히트맵</button><button data-layer="points" type="button">주소지 점</button></div>
            <div class="layer-switch basemap-switch" role="group" aria-label="백지도"><button class="active" data-basemap="data" type="button">데이터 백지도</button><button data-basemap="osm" type="button">OpenStreetMap</button></div>
          </div>
          <span id="resolution-badge" class="resolution-badge">H3 · R7</span>
        </div>
        <div id="map-message" class="map-message" aria-live="polite">산업체 분포를 불러오는 중입니다</div>
        <div id="legend" class="legend"></div><div class="map-credit">경계 admdongkor · 2025.12.31</div>
      </section>
      <aside class="insight-panel" aria-label="선택 결과">
        <div class="panel-heading"><div><span>02</span><p>선택 결과</p></div></div>
        <p id="selection-title" class="selection-title">2024 · 전체 산업 · 경기도 전체</p>
        <div class="hero-stat"><span>사업체 레코드</span><strong id="record-count">-</strong><em id="growth-chip">전년 비교 없음</em></div>
        <div class="secondary-stat"><span id="address-label">고유 주소지</span><strong id="address-count">-</strong></div>
        <section class="trend-section"><div class="section-title"><span>연도별 추이</span><small>사업체 레코드</small></div><div id="trend-chart" class="trend-chart"></div></section>
        <section class="selected-industries"><div class="section-title"><span>선택 산업분류</span><small>단계별 선택 항목</small></div><div id="selected-industry-list" class="selected-industry-list"></div></section>
      </aside>
    </section>
  </main>`;

const elements = {
  apiStatus: document.querySelector<HTMLElement>("#api-status")!, yearTabs: document.querySelector<HTMLElement>("#year-tabs")!,
  industrySelectors: document.querySelector<HTMLElement>("#industry-selectors")!, globalSearch: document.querySelector<HTMLInputElement>("#industry-global-search")!,
  searchResults: document.querySelector<HTMLElement>("#industry-search-results")!, sigun: document.querySelector<HTMLSelectElement>("#sigun-select")!, emd: document.querySelector<HTMLSelectElement>("#emd-select")!,
  industryPath: document.querySelector<HTMLElement>("#industry-path")!, metricHelp: document.querySelector<HTMLElement>("#metric-help")!, mapMessage: document.querySelector<HTMLElement>("#map-message")!,
  legend: document.querySelector<HTMLElement>("#legend")!, resolutionBadge: document.querySelector<HTMLElement>("#resolution-badge")!, selectionTitle: document.querySelector<HTMLElement>("#selection-title")!,
  recordCount: document.querySelector<HTMLElement>("#record-count")!, addressCount: document.querySelector<HTMLElement>("#address-count")!, addressLabel: document.querySelector<HTMLElement>("#address-label")!,
  growthChip: document.querySelector<HTMLElement>("#growth-chip")!, trendChart: document.querySelector<HTMLElement>("#trend-chart")!, selectedIndustryList: document.querySelector<HTMLElement>("#selected-industry-list")!,
  overlay: document.querySelector<HTMLCanvasElement>("#map-overlay")!,
};

const selections: Record<SelectableLevel, Map<string, string>> = { major: new Map(), middle: new Map(), minor: new Map(), detail: new Map() };
const options: Record<SelectableLevel, DimensionItem[]> = { major: [], middle: [], minor: [], detail: [] };
const localQueries: Record<SelectableLevel, string> = { major: "", middle: "", minor: "", detail: "" };
const state = { year: 2024, years: [2019, 2020, 2021, 2022, 2023, 2024], growthBreakYears: [2024], metric: "density" as Metric, layer: "heat" as LayerMode, basemap: "data" as BasemapMode, regionName: "경기도 전체", resolution: 7, openLevel: null as SelectableLevel | null };
let sigunBoundary: FeatureCollection | null = null;
let emdBoundary: FeatureCollection | null = null;
let mapRequest: AbortController | null = null;
let detailRequest: AbortController | null = null;
let refreshTimer = 0;
let overlayFrame = 0;
let searchTimer = 0;
let lastCells: ApiFeatureCollection | null = null;
let lastPoints: ApiFeatureCollection | null = null;
let mapReady = false;

const map = new maplibregl.Map({
  container: "map", center: [127.15, 37.53], zoom: 7.15, minZoom: 6.7, maxZoom: 16, maxBounds: [[126.25, 36.75], [128.15, 38.45]],
  style: {
    version: 8,
    sources: { "osm-tiles": { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "© OpenStreetMap contributors" } },
    layers: [
      { id: "data-basemap", type: "raster", source: "osm-tiles", layout: { visibility: "visible" }, paint: { "raster-saturation": -1, "raster-contrast": -.18, "raster-brightness-min": .18, "raster-brightness-max": 1, "raster-opacity": .7 } },
      { id: "osm-basemap", type: "raster", source: "osm-tiles", layout: { visibility: "none" } },
    ],
  },
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");

function queryString(values: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => { if (value !== undefined && value !== "") params.set(key, String(value)); });
  return params.toString();
}
async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) { const body = await response.json().catch(() => ({})) as { detail?: string }; throw new Error(body.detail ?? `HTTP ${response.status}`); }
  return response.json() as Promise<T>;
}
function activeIndustry(): { level: IndustryLevel; keys: string[]; name: string } {
  for (const level of [...levels].reverse()) {
    const selected = selections[level];
    if (selected.size) { const names = [...selected.values()]; return { level, keys: [...selected.keys()], name: names.length === 1 ? names[0] : `${names[0]} 외 ${names.length - 1}개` }; }
  }
  return { level: "all", keys: ["ALL"], name: "전체 산업" };
}
function commonIndustryParams(): Record<string, string> { const active = activeIndustry(); return { industry_level: active.level, industry_keys: active.keys.join(",") }; }
function selectedRegionCode(): string { return elements.emd.value || elements.sigun.value; }
function resolutionForZoom(zoom: number): number { return zoom >= 11.2 ? 9 : zoom >= 8.8 ? 8 : 7; }
async function loadIndustries(level: SelectableLevel, parents: string[] = []): Promise<DimensionItem[]> {
  const payload = await getJson<{ items: DimensionItem[] }>(`/api/industries?${queryString({ level, year: state.year, parents: parents.join(","), limit: 5000 })}`); return payload.items;
}
function clearDescendants(level: SelectableLevel): void {
  levels.slice(levels.indexOf(level) + 1).forEach((child) => { selections[child].clear(); options[child] = []; localQueries[child] = ""; });
}
function pruneSelection(level: SelectableLevel): void { const allowed = new Set(options[level].map((item) => item.industry_key)); for (const key of selections[level].keys()) if (!allowed.has(key)) selections[level].delete(key); }
function refreshSelectionLabels(level: SelectableLevel): void { const labels = new Map(options[level].map((item) => [item.industry_key!, item.industry_name ?? item.industry_key!])); for (const key of selections[level].keys()) { const label = labels.get(key); if (label) selections[level].set(key, label); } }
async function reloadIndustriesForYear(): Promise<void> { options.major = await loadIndustries("major"); pruneSelection("major"); refreshSelectionLabels("major"); let parent: SelectableLevel = "major"; while (nextLevel[parent]) { const child: SelectableLevel = nextLevel[parent]!; const keys = [...selections[parent].keys()]; options[child] = keys.length ? await loadIndustries(child, keys) : []; pruneSelection(child); refreshSelectionLabels(child); parent = child; } renderIndustrySelectors(); updateSelectionText(); }
async function loadDescendantOptions(from: SelectableLevel): Promise<void> {
  let parent = from;
  while (nextLevel[parent]) { const child = nextLevel[parent]!; const parentKeys = [...selections[parent].keys()]; options[child] = parentKeys.length ? await loadIndustries(child, parentKeys) : []; pruneSelection(child); parent = child; }
}

function renderIndustrySelectors(): void {
  elements.industrySelectors.replaceChildren();
  levels.forEach((level) => {
    const selected = selections[level]; const available = options[level]; const disabled = level !== "major" && available.length === 0;
    const wrapper = document.createElement("div"); wrapper.className = `multi-select${state.openLevel === level ? " open" : ""}${disabled ? " disabled" : ""}`;
    const toggle = document.createElement("button"); toggle.type = "button"; toggle.className = "multi-toggle"; toggle.disabled = disabled; toggle.setAttribute("aria-expanded", String(state.openLevel === level));
    toggle.innerHTML = `<span><small>${levelLabels[level]}</small><b>${selected.size ? `${selected.size}개 선택` : "전체"}</b></span><i></i>`;
    toggle.addEventListener("click", () => { state.openLevel = state.openLevel === level ? null : level; renderIndustrySelectors(); }); wrapper.append(toggle);
    if (state.openLevel === level && !disabled) {
      const panel = document.createElement("div"); panel.className = "multi-panel";
      const search = document.createElement("input"); search.type = "search"; search.value = localQueries[level]; search.placeholder = `${levelLabels[level]} 목록에서 찾기`;
      panel.append(search);
      const allRow = document.createElement("button"); allRow.type = "button"; allRow.className = `all-option${selected.size === 0 ? " active" : ""}`; allRow.textContent = selected.size ? "선택 모두 해제 (전체)" : "전체 적용 중";
      allRow.addEventListener("click", () => { selections[level].clear(); clearDescendants(level); state.openLevel = null; renderIndustrySelectors(); industrySelectionChanged(); }); panel.append(allRow);
      const query = localQueries[level].trim().toLocaleLowerCase("ko-KR");
      const list = document.createElement("div"); list.className = "option-list";
      const emptyMessage = document.createElement("p"); emptyMessage.className = "empty-options"; emptyMessage.textContent = "검색 결과가 없습니다.";
      available.forEach((item) => {
        const key = item.industry_key!; const label = document.createElement("label"); label.className = "check-option";
        label.hidden = !(item.industry_name ?? "").toLocaleLowerCase("ko-KR").includes(query);
        const checkbox = document.createElement("input"); checkbox.type = "checkbox"; checkbox.checked = selected.has(key);
        const text = document.createElement("span"); text.textContent = item.industry_name ?? "";
        checkbox.addEventListener("change", async () => {
          if (checkbox.checked && selected.size >= 100) { checkbox.checked = false; elements.mapMessage.textContent = "한 단계에서 최대 100개까지 선택할 수 있습니다"; elements.mapMessage.classList.add("visible"); return; }
          if (checkbox.checked) selected.set(key, item.industry_name ?? key); else selected.delete(key);
          clearDescendants(level); const child = nextLevel[level]; if (child && selected.size) options[child] = await loadIndustries(child, [...selected.keys()]);
          renderIndustrySelectors(); industrySelectionChanged();
        });
        label.append(checkbox, text); list.append(label);
      });
      emptyMessage.hidden = available.some((item) => (item.industry_name ?? "").toLocaleLowerCase("ko-KR").includes(query)); list.append(emptyMessage);
      search.addEventListener("input", () => {
        localQueries[level] = search.value; const value = search.value.trim().toLocaleLowerCase("ko-KR"); let visible = 0;
        list.querySelectorAll<HTMLLabelElement>(".check-option").forEach((label) => { label.hidden = !label.innerText.toLocaleLowerCase("ko-KR").includes(value); if (!label.hidden) visible += 1; });
        emptyMessage.hidden = visible > 0;
      });
      panel.append(list); wrapper.append(panel);
    }
    elements.industrySelectors.append(wrapper);
  });
}

function updateSelectionText(): void {
  const active = activeIndustry(); elements.selectionTitle.textContent = `${state.year} · ${active.name} · ${state.regionName}`;
  const parts = levels.flatMap((level) => selections[level].size ? [`${levelLabels[level]} ${selections[level].size}개`] : []);
  elements.industryPath.textContent = parts.length ? `${parts.join(" · ")} / 지도 집계: ${levelLabels[active.level as SelectableLevel]}` : "전체 산업";
  renderSelectedIndustries();
  const lq = document.querySelector<HTMLButtonElement>('[data-metric="lq"]')!; lq.disabled = active.level === "all";
  if (lq.disabled && state.metric === "lq") state.metric = "density"; updateMetricUi();
  const growth = document.querySelector<HTMLButtonElement>('[data-metric="growth"]')!; growth.disabled = state.year === state.years[0] || state.growthBreakYears.includes(state.year);
  growth.title = state.growthBreakYears.includes(state.year) ? "10차·11차 분류체계 전환으로 전년 비교를 제공하지 않습니다." : "";
  if (growth.disabled && state.metric === "growth") state.metric = "density"; updateMetricUi();
}
function renderSelectedIndustries(): void {
  elements.selectedIndustryList.replaceChildren();
  levels.forEach((level) => {
    const group = document.createElement("section"); group.className = "selected-industry-group";
    const heading = document.createElement("div"); heading.className = "selected-industry-heading";
    const label = document.createElement("strong"); label.textContent = levelLabels[level];
    const count = document.createElement("span"); count.textContent = selections[level].size ? `${selections[level].size}개` : "전체";
    heading.append(label, count); group.append(heading);
    if (selections[level].size) {
      const list = document.createElement("ul");
      selections[level].forEach((name) => { const item = document.createElement("li"); item.textContent = name; list.append(item); });
      group.append(list);
    } else {
      const empty = document.createElement("p"); empty.textContent = "선택 없음 (전체 적용)"; group.append(empty);
    }
    elements.selectedIndustryList.append(group);
  });
}
function industrySelectionChanged(): void { updateSelectionText(); void refreshDetails(); scheduleMapRefresh(); }
function updateMetricUi(): void {
  const descriptions: Record<Metric, string> = {
    density: "사업체가 밀집된 절대적 중심지를 보여줍니다.",
    lq: "경기도 평균보다 해당 산업 비중이 높은 곳을 보여줍니다.",
    growth: "이전 조사연도와 비교한 사업체 변화율을 보여줍니다.",
  };
  elements.metricHelp.textContent = descriptions[state.metric];
  document.querySelectorAll<HTMLButtonElement>("[data-metric]").forEach((button) => button.classList.toggle("active", button.dataset.metric === state.metric));
}
function renderLegend(scale?: Record<string, unknown>): void {
  if (state.metric === "growth") { elements.legend.innerHTML = `<span>감소</span><i class="legend-ramp growth"></i><span>증가</span>`; return; }
  const max = Number(scale?.p95 ?? 0); const label = state.metric === "density" ? `고밀도 ${max ? numberFormat.format(max) : ""}` : `고특화 LQ ${max ? max.toFixed(1) : ""}`;
  elements.legend.innerHTML = `<span>낮음</span><i class="legend-ramp ${state.metric}"></i><span>${label}</span>`;
}
function normalizedFeatures(payload: ApiFeatureCollection): FeatureCollection<Point, Record<string, unknown>> {
  const scale = payload.meta.scale as Record<string, unknown> | undefined; const cap = Math.max(Number(scale?.p95 ?? 1), state.metric === "lq" ? 2 : 1);
  return { type: "FeatureCollection", features: payload.features.map((feature) => { const value = Number(feature.properties?.display_value ?? 0); return { type: "Feature", id: feature.id, geometry: { type: "Point", coordinates: [Number(feature.properties?.center_lon), Number(feature.properties?.center_lat)] }, properties: { ...feature.properties, intensity: Math.min(Math.max(value / cap, .05), 1) } }; }) };
}
function pureGeoJson(payload: ApiFeatureCollection): FeatureCollection<Geometry, Record<string, unknown>> { return { type: "FeatureCollection", features: payload.features }; }
function setHeatPalette(): void {
  if (!map.getLayer("industry-heat")) return;
  const colors = state.metric === "lq" ? ["rgba(15,54,53,0)", "#8bc8b6", "#f1d47b", "#f28f4b", "#b32f2f"] : ["rgba(21,53,47,0)", "#f2d27e", "#ef9953", "#d94f38", "#6f1328"];
  map.setPaintProperty("industry-heat", "heatmap-color", ["interpolate", ["linear"], ["heatmap-density"], 0, colors[0], .2, colors[1], .45, colors[2], .72, colors[3], 1, colors[4]]);
}
function updateLayerVisibility(): void {
  if (!map.getLayer("industry-heat")) return; const heatVisible = state.layer === "heat" && state.metric !== "growth";
  map.setLayoutProperty("industry-heat", "visibility", heatVisible ? "visible" : "none"); map.setLayoutProperty("hotspot-points", "visibility", heatVisible ? "visible" : "none");
  map.setLayoutProperty("growth-cells", "visibility", state.layer === "heat" && state.metric === "growth" ? "visible" : "none"); map.setLayoutProperty("address-points", "visibility", state.layer === "points" ? "visible" : "none");
}
function growthColor(value: number): string { const strength = Math.min(Math.abs(value), 1); return value < 0 ? `rgba(8, 127, 122, ${.22 + strength * .58})` : `rgba(169, 55, 43, ${.18 + strength * .62})`; }
function traceRing(context: CanvasRenderingContext2D, ring: number[][]): void { ring.forEach((coordinate, index) => { const point = map.project(coordinate as [number, number]); if (index === 0) context.moveTo(point.x, point.y); else context.lineTo(point.x, point.y); }); }
function drawBoundaryCollection(context: CanvasRenderingContext2D, collection: FeatureCollection | null, color: string, width: number, filter?: (feature: Feature) => boolean): void {
  if (!collection) return; context.save(); context.strokeStyle = color; context.lineWidth = width; context.lineJoin = "round";
  collection.features.forEach((feature) => {
    if (filter && !filter(feature)) return; const geometry = feature.geometry as Polygon | MultiPolygon; if (geometry.type !== "Polygon" && geometry.type !== "MultiPolygon") return;
    const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
    polygons.forEach((polygon) => { context.beginPath(); polygon.forEach((ring) => traceRing(context, ring)); context.stroke(); });
  }); context.restore();
}
function drawOverlay(): void {
  const canvas = elements.overlay; const width = canvas.clientWidth; const height = canvas.clientHeight; const ratio = window.devicePixelRatio || 1;
  if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) { canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio); }
  const context = canvas.getContext("2d"); if (!context) return; context.setTransform(ratio, 0, 0, ratio, 0, 0); context.clearRect(0, 0, width, height);
  const features = state.layer === "points" ? lastPoints?.features : lastCells?.features;
  if (features && state.layer === "points") {
    features.forEach((feature) => { if (feature.geometry.type !== "Point") return; const point = map.project(feature.geometry.coordinates as [number, number]); const count = Number(feature.properties?.record_count ?? 1); context.beginPath(); context.arc(point.x, point.y, Math.min(10, 2 + Math.log1p(count)), 0, Math.PI * 2); context.fillStyle = "rgba(220, 78, 43, .72)"; context.fill(); context.strokeStyle = "rgba(255, 248, 233, .8)"; context.lineWidth = .7; context.stroke(); });
  } else if (features && state.metric === "growth") {
    features.forEach((feature) => { if (feature.geometry.type !== "Polygon") return; context.beginPath(); traceRing(context, feature.geometry.coordinates[0] as number[][]); context.closePath(); context.fillStyle = growthColor(Number(feature.properties?.display_value ?? 0)); context.fill(); });
  } else if (features) {
    features.forEach((feature) => {
      const lon = Number(feature.properties?.center_lon); const lat = Number(feature.properties?.center_lat); const intensity = Number(feature.properties?.intensity ?? 0); if (!Number.isFinite(lon) || !Number.isFinite(lat) || intensity < .08) return;
      const point = map.project([lon, lat]); const radius = 4 + intensity * (state.resolution === 7 ? 13 : 10); const gradient = context.createRadialGradient(point.x, point.y, 0, point.x, point.y, radius); const coreAlpha = .08 + intensity * .34;
      const lqColor = intensity < .35 ? "53, 139, 128" : intensity < .65 ? "218, 156, 58" : "178, 48, 47"; const color = state.metric === "lq" ? lqColor : "130, 24, 44";
      gradient.addColorStop(0, `rgba(${color}, ${coreAlpha})`); gradient.addColorStop(.48, `rgba(${color}, ${.02 + intensity * .13})`); gradient.addColorStop(1, `rgba(${color}, 0)`); context.beginPath(); context.arc(point.x, point.y, radius, 0, Math.PI * 2); context.fillStyle = gradient; context.fill();
    });
  }
  drawBoundaryCollection(context, sigunBoundary, "rgba(15, 15, 15, .9)", map.getZoom() > 10 ? 1.5 : 1.1);
  if (map.getZoom() >= 10.5) drawBoundaryCollection(context, emdBoundary, "rgba(38, 38, 38, .72)", .75);
  if (elements.sigun.value) drawBoundaryCollection(context, sigunBoundary, "#000", 3, (feature) => String(feature.properties?.siguncd) === elements.sigun.value);
}
function scheduleOverlayDraw(): void { window.cancelAnimationFrame(overlayFrame); overlayFrame = window.requestAnimationFrame(drawOverlay); }
function currentBoundsParams(): Record<string, number> { const bounds = map.getBounds(); return { west: bounds.getWest(), south: bounds.getSouth(), east: bounds.getEast(), north: bounds.getNorth() }; }

async function refreshMap(): Promise<void> {
  if (!mapReady) return;
  mapRequest?.abort(); mapRequest = new AbortController(); state.resolution = resolutionForZoom(map.getZoom()); elements.resolutionBadge.textContent = `H3 · R${state.resolution}`;
  elements.mapMessage.textContent = state.layer === "heat" ? "히트맵을 계산하는 중입니다" : "주소지 점을 불러오는 중입니다"; elements.mapMessage.classList.add("visible");
  const common = { year: state.year, ...commonIndustryParams(), ...currentBoundsParams() };
  try {
    if (state.layer === "points") {
      const payload = await getJson<ApiFeatureCollection>(`/api/map/points?${queryString({ ...common, limit: 5000 })}`, mapRequest.signal); lastPoints = payload; (map.getSource("address-source") as GeoJSONSource).setData(pureGeoJson(payload));
      elements.mapMessage.textContent = payload.meta.truncated ? "점이 많아 상위 5,000개 주소지만 표시합니다" : `${numberFormat.format(payload.features.length)}개 주소지 표시`;
    } else {
      const payload = await getJson<ApiFeatureCollection>(`/api/map/cells?${queryString({ ...common, resolution: state.resolution, metric: state.metric })}`, mapRequest.signal); lastCells = payload;
      if (payload.meta.aggregation_required) { elements.mapMessage.textContent = "표시량이 많습니다. 지도를 축소해 주세요"; return; }
      const normalized = normalizedFeatures(payload); normalized.features.forEach((feature) => { const original = payload.features.find((item) => item.id === feature.id); if (original?.properties) original.properties.intensity = feature.properties?.intensity; });
      (map.getSource("cell-source") as GeoJSONSource).setData(pureGeoJson(payload)); (map.getSource("heat-source") as GeoJSONSource).setData(normalized); renderLegend(payload.meta.scale as Record<string, unknown> | undefined); elements.mapMessage.textContent = `${numberFormat.format(payload.features.length)}개 격자 표시`;
    }
    updateLayerVisibility(); scheduleOverlayDraw(); window.setTimeout(() => elements.mapMessage.classList.remove("visible"), 900);
  } catch (error) { if ((error as Error).name === "AbortError") return; elements.mapMessage.textContent = (error as Error).message; }
}
function scheduleMapRefresh(): void { window.clearTimeout(refreshTimer); refreshTimer = window.setTimeout(() => void refreshMap(), 220); }
function renderTrend(items: TrendItem[]): void {
  elements.trendChart.replaceChildren(); const max = Math.max(...items.map((item) => item.record_count), 1);
  items.forEach((item) => { const column = document.createElement("div"); column.className = "trend-column"; column.title = `${item.year}: ${numberFormat.format(item.record_count)}`; const value = document.createElement("span"); value.textContent = numberFormat.format(item.record_count); const bar = document.createElement("i"); bar.style.height = `${Math.max(8, item.record_count / max * 100)}%`; bar.classList.toggle("selected", item.year === state.year); const year = document.createElement("small"); year.textContent = String(item.year).slice(2); column.append(value, bar, year); elements.trendChart.append(column); });
}
async function refreshDetails(): Promise<void> {
  detailRequest?.abort(); detailRequest = new AbortController(); updateSelectionText(); const common = { ...commonIndustryParams(), region_code: selectedRegionCode() };
  try {
    const [summary, trend] = await Promise.all([getJson<Summary>(`/api/summary?${queryString({ ...common, year: state.year })}`, detailRequest.signal), getJson<{ items: TrendItem[] }>(`/api/trend?${queryString(common)}`, detailRequest.signal)]);
    elements.recordCount.textContent = numberFormat.format(summary.record_count); elements.addressCount.textContent = numberFormat.format(summary.address_count); elements.addressLabel.textContent = summary.address_count_method === "sum_by_industry" ? "산업별 주소 합계" : "고유 주소지";
    elements.growthChip.textContent = summary.growth_rate === null ? "전년 비교 없음" : `전년 대비 ${percentFormat.format(summary.growth_rate)}`; elements.growthChip.dataset.direction = summary.growth_rate === null ? "none" : summary.growth_rate >= 0 ? "up" : "down"; renderTrend(trend.items);
  } catch (error) { if ((error as Error).name !== "AbortError") elements.apiStatus.textContent = "요약 조회 실패"; }
}
function setRegionOptions(select: HTMLSelectElement, items: DimensionItem[], placeholder: string): void { select.replaceChildren(new Option(placeholder, "")); items.forEach((item) => select.add(new Option(item.region_name ?? "", item.region_code ?? ""))); select.disabled = items.length === 0; }
function geometryBounds(feature: Feature): LngLatBoundsLike | null {
  const geometry = feature.geometry as Polygon | MultiPolygon; if (geometry.type !== "Polygon" && geometry.type !== "MultiPolygon") return null; const coordinates = geometry.type === "Polygon" ? geometry.coordinates.flat(1) : geometry.coordinates.flat(2);
  let west = Infinity; let south = Infinity; let east = -Infinity; let north = -Infinity; coordinates.forEach(([lon, lat]) => { west = Math.min(west, lon); east = Math.max(east, lon); south = Math.min(south, lat); north = Math.max(north, lat); }); return [[west, south], [east, north]];
}
function fitRegion(collection: FeatureCollection | null, property: string, code: string): void { const feature = collection?.features.find((item) => String(item.properties?.[property]) === code); if (!feature) return; const bounds = geometryBounds(feature); if (bounds) map.fitBounds(bounds, { padding: 48, duration: 850, maxZoom: property === "emdcd" ? 13 : 10.3 }); }
function searchResultName(item: DimensionItem, level: SelectableLevel): string | undefined { if (level === item.industry_level) return item.industry_name; return item[`${level}_name` as "major_name" | "middle_name" | "minor_name"]; }
async function selectSearchResult(item: DimensionItem): Promise<void> {
  const target = item.industry_level!; clearDescendants(target); const targetIndex = levels.indexOf(target);
  levels.slice(0, targetIndex + 1).forEach((level) => { const key = item[`${level}_key` as "major_key" | "middle_key" | "minor_key" | "detail_key"]; const name = searchResultName(item, level); if (key && name) selections[level].set(key, name); });
  await loadDescendantOptions("major"); elements.globalSearch.value = ""; elements.searchResults.hidden = true; state.openLevel = target; renderIndustrySelectors(); industrySelectionChanged();
}
async function runIndustrySearch(): Promise<void> {
  const query = elements.globalSearch.value.trim(); if (!query) { elements.searchResults.hidden = true; return; }
  const payload = await getJson<{ items: DimensionItem[] }>(`/api/industries/search?${queryString({ q: query, year: state.year, limit: 80 })}`); elements.searchResults.replaceChildren();
  payload.items.forEach((item) => { const button = document.createElement("button"); button.type = "button"; button.className = "search-result"; const level = item.industry_level!; const breadcrumb = [item.major_name, item.middle_name, item.minor_name].filter((name, index, array) => name && array.indexOf(name) === index && name !== item.industry_name).join(" › "); button.innerHTML = `<span class="level-badge ${level}">${levelLabels[level]}</span><span><b>${item.industry_name}</b>${breadcrumb ? `<small>${breadcrumb}</small>` : ""}</span>`; button.addEventListener("click", () => void selectSearchResult(item)); elements.searchResults.append(button); });
  if (!payload.items.length) elements.searchResults.innerHTML = `<p class="empty-options">검색 결과가 없습니다.</p>`; elements.searchResults.hidden = false;
}
async function initializeFilters(): Promise<void> {
  const [meta, majors, siguns, sigunGeo, emdGeo] = await Promise.all([getJson<DashboardMeta>("/api/meta"), loadIndustries("major"), getJson<{ items: DimensionItem[] }>("/api/regions?level=sigun"), getJson<FeatureCollection>("/api/boundaries/sigun"), getJson<FeatureCollection>("/api/boundaries/emd")]);
  state.years = meta.analysis_years; state.year = state.years.at(-1) ?? 2024; state.growthBreakYears = meta.classification.growth_break_years; options.major = majors; sigunBoundary = sigunGeo; emdBoundary = emdGeo; renderIndustrySelectors(); setRegionOptions(elements.sigun, siguns.items, "경기도 전체"); elements.yearTabs.replaceChildren();
  state.years.forEach((year) => { const button = document.createElement("button"); button.type = "button"; button.textContent = String(year); button.className = year === state.year ? "active" : ""; button.addEventListener("click", async () => { state.year = year; elements.yearTabs.querySelectorAll("button").forEach((item) => item.classList.toggle("active", item === button)); await reloadIndustriesForYear(); void refreshDetails(); scheduleMapRefresh(); }); elements.yearTabs.append(button); });
  elements.apiStatus.textContent = "산업체 DB 연결됨"; elements.apiStatus.classList.add("ready"); updateSelectionText(); scheduleOverlayDraw();
}

elements.globalSearch.addEventListener("input", () => { window.clearTimeout(searchTimer); searchTimer = window.setTimeout(() => void runIndustrySearch(), 250); });
elements.globalSearch.addEventListener("focus", () => { if (elements.globalSearch.value.trim()) void runIndustrySearch(); });
document.addEventListener("click", (event) => { if (!(event.target as Element).closest(".multi-select") && state.openLevel) { state.openLevel = null; renderIndustrySelectors(); } if (!(event.target as Element).closest(".global-search-wrap")) elements.searchResults.hidden = true; });
elements.sigun.addEventListener("change", async () => {
  elements.emd.replaceChildren(new Option("행정동 전체", ""));
  if (elements.sigun.value) { const payload = await getJson<{ items: DimensionItem[] }>(`/api/regions?${queryString({ level: "emd", parent: elements.sigun.value })}`); setRegionOptions(elements.emd, payload.items, "행정동 전체"); state.regionName = elements.sigun.selectedOptions[0].text; fitRegion(sigunBoundary, "siguncd", elements.sigun.value); }
  else { elements.emd.disabled = true; state.regionName = "경기도 전체"; map.fitBounds([[126.35, 36.9], [127.85, 38.25]], { padding: 28, duration: 850 }); }
  map.setFilter("selected-sigun", elements.sigun.value ? ["==", ["get", "siguncd"], elements.sigun.value] : ["==", ["get", "siguncd"], ""]); void refreshDetails(); scheduleOverlayDraw();
});
elements.emd.addEventListener("change", () => { state.regionName = elements.emd.value ? elements.emd.selectedOptions[0].text : elements.sigun.selectedOptions[0].text; if (elements.emd.value) fitRegion(emdBoundary, "emdcd", elements.emd.value); void refreshDetails(); scheduleMapRefresh(); });
document.querySelectorAll<HTMLButtonElement>("[data-metric]").forEach((button) => button.addEventListener("click", () => { if (button.disabled) return; state.metric = button.dataset.metric as Metric; updateMetricUi(); setHeatPalette(); updateLayerVisibility(); scheduleMapRefresh(); }));
document.querySelectorAll<HTMLButtonElement>("[data-layer]").forEach((button) => button.addEventListener("click", () => { state.layer = button.dataset.layer as LayerMode; document.querySelectorAll<HTMLButtonElement>("[data-layer]").forEach((item) => item.classList.toggle("active", item === button)); updateLayerVisibility(); scheduleMapRefresh(); }));
document.querySelectorAll<HTMLButtonElement>("[data-basemap]").forEach((button) => button.addEventListener("click", () => {
  if (!mapReady || !map.getLayer("osm-basemap")) return;
  state.basemap = button.dataset.basemap as BasemapMode;
  map.setLayoutProperty("data-basemap", "visibility", state.basemap === "data" ? "visible" : "none"); map.setLayoutProperty("osm-basemap", "visibility", state.basemap === "osm" ? "visible" : "none"); document.querySelectorAll<HTMLButtonElement>("[data-basemap]").forEach((item) => item.classList.toggle("active", item === button));
}));
document.querySelector<HTMLButtonElement>("#reset-filter")!.addEventListener("click", () => window.location.reload());

map.on("style.load", async () => {
  map.addSource("cell-source", { type: "geojson", data: emptyCollection }); map.addSource("heat-source", { type: "geojson", data: emptyCollection }); map.addSource("address-source", { type: "geojson", data: emptyCollection }); map.addSource("sigun-boundary", { type: "geojson", data: "/api/boundaries/sigun" }); map.addSource("emd-boundary", { type: "geojson", data: "/api/boundaries/emd" });
  map.addLayer({ id: "industry-heat", type: "heatmap", source: "heat-source", maxzoom: 14, paint: { "heatmap-weight": ["get", "intensity"], "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 7, 1.15, 13, 2.2], "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 7, 20, 13, 34], "heatmap-opacity": .88 } });
  map.addLayer({ id: "hotspot-points", type: "circle", source: "heat-source", paint: { "circle-radius": ["interpolate", ["linear"], ["coalesce", ["get", "intensity"], 0], 0, 1.5, 1, 5], "circle-color": "#d94f38", "circle-opacity": .65 } });
  map.addLayer({ id: "growth-cells", type: "fill", source: "cell-source", layout: { visibility: "none" }, paint: { "fill-color": ["interpolate", ["linear"], ["coalesce", ["get", "display_value"], 0], -1, "#087f7a", -.25, "#72b7aa", 0, "#eee4cc", .25, "#e99a51", 1, "#a9372b"], "fill-opacity": .78 } });
  map.addLayer({ id: "address-points", type: "circle", source: "address-source", layout: { visibility: "none" }, paint: { "circle-radius": ["interpolate", ["linear"], ["coalesce", ["get", "record_count"], 1], 1, 2.5, 20, 7, 100, 12], "circle-color": "#e55d36", "circle-opacity": .72, "circle-stroke-color": "#fff8e9", "circle-stroke-width": .8 } });
  map.addLayer({ id: "emd-lines", type: "line", source: "emd-boundary", minzoom: 10.5, paint: { "line-color": "#2c2c2c", "line-opacity": .72, "line-width": .9 } });
  map.addLayer({ id: "sigun-lines", type: "line", source: "sigun-boundary", paint: { "line-color": "#111", "line-opacity": .95, "line-width": ["interpolate", ["linear"], ["zoom"], 7, 1.3, 11, 2.5] } });
  map.addLayer({ id: "selected-sigun", type: "line", source: "sigun-boundary", filter: ["==", ["get", "siguncd"], ""], paint: { "line-color": "#000", "line-width": 4, "line-opacity": 1 } }); setHeatPalette(); mapReady = true;
  try { await initializeFilters(); await Promise.all([refreshDetails(), refreshMap()]); } catch (error) { elements.apiStatus.textContent = "API 연결 실패"; elements.mapMessage.textContent = (error as Error).message; elements.mapMessage.classList.add("visible"); }
});
map.on("moveend", () => { if (mapReady) scheduleMapRefresh(); }); map.on("move", scheduleOverlayDraw); map.on("resize", scheduleOverlayDraw);
map.on("click", "growth-cells", (event: MapLayerMouseEvent) => { const properties = event.features?.[0]?.properties; if (!properties) return; const value = Number(properties.display_value ?? 0); new maplibregl.Popup({ closeButton: false, offset: 8 }).setLngLat(event.lngLat).setHTML(`<strong>${percentFormat.format(value)}</strong><span>${numberFormat.format(Number(properties.record_count ?? 0))}개 사업체</span>`).addTo(map); });
map.on("click", "address-points", (event: MapLayerMouseEvent) => { const properties = event.features?.[0]?.properties; if (!properties) return; new maplibregl.Popup({ closeButton: false, offset: 8 }).setLngLat(event.lngLat).setHTML(`<strong>${String(properties.source_address ?? "주소 정보 없음")}</strong><span>${numberFormat.format(Number(properties.record_count ?? 0))}개 사업체 레코드</span>`).addTo(map); });
updateMetricUi(); renderLegend();
