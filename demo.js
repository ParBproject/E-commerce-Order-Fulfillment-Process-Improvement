const state = {
  period: "pilot",
  facility: "all",
  data: null,
};

const SHIFT_ORDER = ["Days", "Swing", "Night"];

const $ = (sel) => document.querySelector(sel);

const num = (value, digits = 1) =>
  Number(value).toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

const int = (value) =>
  Number(value).toLocaleString("en-US", { maximumFractionDigits: 0 });

const usd = (value) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);

function readQuery() {
  const params = new URLSearchParams(window.location.search);
  const period = params.get("period");
  const building = params.get("building");
  if (period === "baseline" || period === "pilot") state.period = period;
  if (building) state.facility = building;
}

function writeQuery() {
  const params = new URLSearchParams();
  params.set("period", state.period);
  if (state.facility !== "all") params.set("building", state.facility);
  const next = `${window.location.pathname}?${params.toString()}`;
  window.history.replaceState(null, "", next);
}

function periodRow(data) {
  return data.kpi_period.find((row) => row.period === state.period);
}

function otherRow(data) {
  const other = state.period === "pilot" ? "baseline" : "pilot";
  return data.kpi_period.find((row) => row.period === other);
}

function facilityName(data, facilityId) {
  const match = (data.facilities || []).find((row) => row.facility_id === facilityId);
  return match ? match.name : facilityId;
}

function fillBuildings(data) {
  const select = $("#building");
  const previous = state.facility;
  select.replaceChildren(new Option("Network", "all"));
  (data.facilities || []).forEach((facility) => {
    select.append(new Option(facility.name, facility.facility_id));
  });
  const known = [...select.options].some((option) => option.value === previous);
  state.facility = known ? previous : "all";
  select.value = state.facility;
}

function card(label, value, detail, hot) {
  const node = document.createElement("article");
  node.className = hot ? "card hot" : "card";
  const k = document.createElement("div");
  k.className = "k";
  k.textContent = label;
  const v = document.createElement("div");
  v.className = "v";
  v.textContent = value;
  const s = document.createElement("p");
  s.className = "s";
  s.textContent = detail;
  node.append(k, v, s);
  return node;
}

function renderCards(data) {
  const row = periodRow(data);
  const other = otherRow(data);
  const otherLabel = other.period === "baseline" ? "Baseline" : "Pilot";
  const host = $("#cards");
  host.replaceChildren(
    card("Cartons", int(row.orders), `${otherLabel} ${int(other.orders)}`, false),
    card(
      "Median dock-to-stage",
      `${num(row.median_cycle)} min`,
      `${otherLabel} ${num(other.median_cycle)} min`,
      true,
    ),
    card("P90", `${num(row.p90_cycle)} min`, `${otherLabel} ${num(other.p90_cycle)} min`, false),
    card(
      "Same-day miss",
      `${num(row.sla_miss_pct)}%`,
      `${otherLabel} ${num(other.sla_miss_pct)}% · gate ${data.sla_minutes} min`,
      true,
    ),
    card(
      "Rework",
      `${num(row.rework_rate_pct)}%`,
      `${otherLabel} ${num(other.rework_rate_pct)}%`,
      false,
    ),
  );
  const label = state.period === "pilot" ? "Pilot" : "Baseline";
  $("#sourceNote").textContent =
    `${label} network scorecard from kpi_period in metrics.json. ` +
    "The building filter changes dwell and shift bays only.";
}

function dwellRows(data) {
  if (state.facility === "all") {
    return data.step_profile.map((row) => ({
      name: row.step_name,
      baseline: row.baseline_avg,
      pilot: row.pilot_avg,
    }));
  }
  const grouped = new Map();
  (data.step_by_facility || [])
    .filter((row) => row.facility_id === state.facility)
    .forEach((row) => {
      const entry = grouped.get(row.step_id) || {
        name: row.step_name,
        seq: row.step_seq,
        baseline: null,
        pilot: null,
      };
      entry[row.period] = row.avg_dwell;
      entry.seq = row.step_seq;
      grouped.set(row.step_id, entry);
    });
  return [...grouped.values()].sort((a, b) => a.seq - b.seq);
}

function renderSteps(data) {
  const rows = dwellRows(data);
  const max = Math.max(
    1,
    ...rows.flatMap((row) => [row.baseline || 0, row.pilot || 0]),
  );
  const host = $("#steps");
  host.replaceChildren();
  rows.forEach((row) => {
    const wrap = document.createElement("div");
    wrap.className = "step";
    const name = document.createElement("div");
    name.className = "step-name";
    name.textContent = row.name;
    const bars = document.createElement("div");
    bars.className = "bars";
    ["baseline", "pilot"].forEach((period) => {
      const bar = document.createElement("div");
      const value = row[period];
      bar.className = `bar ${period}${state.period === period ? "" : " dim"}`;
      bar.style.width = `${Math.max(8, ((value || 0) / max) * 100)}%`;
      bar.textContent = value == null ? "—" : num(value);
      bars.append(bar);
    });
    wrap.append(name, bars);
    host.append(wrap);
  });
  const where =
    state.facility === "all"
      ? "Network averages from step_profile."
      : `${facilityName(data, state.facility)} averages from step_by_facility.`;
  $("#dwellNote").textContent = `${where} The selected scenario is the brighter bar.`;
}

function renderBays(data) {
  const body = $("#bays tbody");
  const rows = (data.facility_shift || [])
    .filter((row) => row.period === state.period)
    .filter((row) => state.facility === "all" || row.facility_id === state.facility)
    .sort((a, b) => {
      const facility = a.facility_id.localeCompare(b.facility_id);
      if (facility !== 0) return facility;
      return SHIFT_ORDER.indexOf(a.shift) - SHIFT_ORDER.indexOf(b.shift);
    });
  body.replaceChildren();
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    [row.facility_name, row.shift, int(row.orders), num(row.median_cycle), num(row.p90_cycle), `${num(row.sla_miss_pct)}%`, `${num(row.rework_pct)}%`]
      .forEach((text) => {
        const td = document.createElement("td");
        td.textContent = text;
        tr.append(td);
      });
    body.append(tr);
  });
}

function fact(text) {
  const node = document.createElement("span");
  node.className = "fact";
  node.textContent = text;
  return node;
}

function renderNotes(data) {
  const host = $("#notes");
  host.replaceChildren();
  (data.brief || []).forEach((sentence) => {
    const p = document.createElement("p");
    p.className = "note";
    p.textContent = sentence;
    host.append(p);
  });
  const money = data.money || {};
  const boot = (data.tests && data.tests.bootstrap) || {};
  const fontana = (data.sla_cells || []).filter((row) => row.cell === "Fontana night");
  const facts = document.createElement("div");
  facts.className = "facts";
  fontana.forEach((row) => {
    const label = row.period === "baseline" ? "Baseline" : "Pilot";
    facts.append(
      fact(`Fontana night ${label.toLowerCase()} miss ${num(row.sla_miss_pct)}% · median ${num(row.median_cycle)} min`),
    );
  });
  if (boot.ci95_low != null) {
    facts.append(
      fact(`Bootstrap median drop ${num(boot.median_delta_minutes)} min (95% CI ${num(boot.ci95_low)}–${num(boot.ci95_high)})`),
    );
  }
  if (money.window_usd != null) {
    facts.append(fact(`Touch labor in window ${usd(money.window_usd)}`));
    facts.append(fact(`Payback ${num(money.payback_months_observed)} months at observed volume`));
    facts.append(fact(`Blended rate $${num(money.blended_labor_rate, 2)}/hr`));
  }
  host.append(facts);
}

function syncToggle() {
  document.querySelectorAll("[data-period]").forEach((button) => {
    button.setAttribute("aria-pressed", button.dataset.period === state.period ? "true" : "false");
  });
}

function render() {
  const data = state.data;
  if (!data) return;
  syncToggle();
  $("#building").value = state.facility;
  renderCards(data);
  renderSteps(data);
  renderBays(data);
  renderNotes(data);
  $("#status").textContent = "";
  writeQuery();
}

function fail(message) {
  $("#sourceNote").textContent = "The scorecard did not load.";
  $("#status").textContent = message;
}

async function main() {
  readQuery();
  document.querySelectorAll("[data-period]").forEach((button) => {
    button.addEventListener("click", () => {
      state.period = button.dataset.period;
      render();
    });
  });
  $("#building").addEventListener("change", (event) => {
    state.facility = event.target.value;
    render();
  });
  try {
    const response = await fetch("dashboard/metrics.json");
    if (!response.ok) throw new Error(`metrics.json returned ${response.status}`);
    state.data = await response.json();
    if (!Array.isArray(state.data.kpi_period)) throw new Error("kpi_period missing");
    fillBuildings(state.data);
    render();
  } catch (error) {
    fail(error instanceof Error ? error.message : "Could not read metrics.json");
  }
}

main();
