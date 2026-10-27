const $ = (sel) => document.querySelector(sel);

const money = (n) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);

const fmt = (n, d = 1) => Number(n).toFixed(d);

function median(values) {
  if (!values.length) return 0;
  const s = [...values].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function quantile(values, q) {
  if (!values.length) return 0;
  const s = [...values].sort((a, b) => a - b);
  const pos = (s.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  if (lo === hi) return s[lo];
  return s[lo] * (hi - pos) + s[hi] * (pos - lo);
}

function mean(values) {
  return values.reduce((a, b) => a + b, 0) / Math.max(values.length, 1);
}

function density(values, lo, hi, bins) {
  const width = (hi - lo) / bins;
  const counts = Array(bins).fill(0);
  values.forEach((v) => {
    if (v < lo || v > hi) return;
    const i = Math.min(bins - 1, Math.floor((v - lo) / width));
    counts[i] += 1;
  });
  const n = Math.max(values.length, 1);
  return counts.map((c, i) => ({
    x0: lo + i * width,
    x1: lo + (i + 1) * width,
    y: c / (n * width),
  }));
}

function pathFrom(bins, h, lo = 30, hi = 260) {
  const w = 640;
  const left = 36;
  const right = 16;
  const top = 12;
  const bottom = 32;
  const innerW = w - left - right;
  const innerH = h - top - bottom;
  const x = (v) => left + ((v - lo) / (hi - lo)) * innerW;
  const y = (p) => top + innerH - p * innerH;
  if (!bins.length) return "";
  let d = `M ${x(bins[0].x0)} ${y(0)}`;
  bins.forEach((b) => {
    d += ` L ${x(b.x0)} ${y(b.y)} L ${x(b.x1)} ${y(b.y)}`;
  });
  d += ` L ${x(bins[bins.length - 1].x1)} ${y(0)} Z`;
  return { d, x, y, left, top, innerW, innerH, bottom };
}

function filterOrders(data, dc, shift) {
  return data.orders.filter((o) => {
    if (dc !== "all" && o.dc !== dc) return false;
    if (shift !== "all" && o.shift !== shift) return false;
    return true;
  });
}

function renderTickets(data, orders) {
  const byPeriod = {
    baseline: orders.filter((o) => o.period === "baseline"),
    pilot: orders.filter((o) => o.period === "pilot"),
  };
  const gate = data.sla_minutes;
  const medB = median(byPeriod.baseline.map((o) => o.mins));
  const medP = median(byPeriod.pilot.map((o) => o.mins));
  const missB = 100 * mean(byPeriod.baseline.map((o) => o.miss));
  const missP = 100 * mean(byPeriod.pilot.map((o) => o.miss));
  const p90B = quantile(byPeriod.baseline.map((o) => o.mins), 0.9);
  const p90P = quantile(byPeriod.pilot.map((o) => o.mins), 0.9);
  const rwB = 100 * mean(byPeriod.baseline.map((o) => o.rw));
  const rwP = 100 * mean(byPeriod.pilot.map((o) => o.rw));
  const drop = medB - medP;
  const cards = [
    {
      k: "Median dock-to-stage",
      v: `${Math.round(medP)}<em>min</em>`,
      h: `Baseline ${Math.round(medB)} min · Δ ${drop.toFixed(1)} min`,
      cls: medP < medB ? "good" : "",
    },
    {
      k: "Same-day miss",
      v: `${missP.toFixed(1)}<em>%</em>`,
      h: `Was ${missB.toFixed(1)}% of cartons past ${gate} min`,
      cls: missP < missB ? "good" : missP > missB ? "alert" : "",
    },
    {
      k: "P90 dock-to-stage",
      v: `${Math.round(p90P)}<em>min</em>`,
      h: `Baseline ${Math.round(p90B)} min`,
      cls: "",
    },
    {
      k: "Rework",
      v: `${rwP.toFixed(1)}<em>%</em>`,
      h: `Baseline ${rwB.toFixed(1)}% · skip-lane + zone pick`,
      cls: rwP < rwB ? "good" : "",
    },
  ];
  $("#tickets").innerHTML = cards
    .map(
      (c) => `<article class="ticket ${c.cls}">
        <div class="k">${c.k}</div>
        <div class="v">${c.v}</div>
        <div class="h">${c.h}</div>
      </article>`
    )
    .join("");
  $("#orderCount").textContent = `${orders.length.toLocaleString()} cartons in view`;
}

function namesById(data) {
  const names = {};
  (data.facilities || []).forEach((row) => {
    names[row.facility_id] = row.name;
  });
  return names;
}

function placeLabel(dc, shift, names) {
  const building = dc === "all" ? "Network" : names[dc] || dc;
  const when = shift === "all" ? "all shifts" : shift;
  return `${building}, ${when}`;
}

function profileFromPeriodRows(rows) {
  const grouped = new Map();
  rows.forEach((row) => {
    const entry = grouped.get(row.step_id) || {
      step_id: row.step_id,
      step_name: row.step_name,
      step_seq: row.step_seq,
      baseline_avg: 0,
      pilot_avg: 0,
    };
    if (row.period === "baseline") entry.baseline_avg = row.avg_dwell;
    if (row.period === "pilot") entry.pilot_avg = row.avg_dwell;
    entry.step_seq = row.step_seq;
    grouped.set(row.step_id, entry);
  });
  return [...grouped.values()].sort((a, b) => a.step_seq - b.step_seq);
}

function dwellSteps(data, dc, shift) {
  if (dc === "all" && shift === "all") return data.step_profile;
  if (dc !== "all" && shift !== "all") {
    return profileFromPeriodRows(
      data.step_by_cell.filter((row) => row.facility_id === dc && row.shift === shift)
    );
  }
  if (shift !== "all") {
    return profileFromPeriodRows(data.step_by_shift.filter((row) => row.shift === shift));
  }
  return profileFromPeriodRows(data.step_by_facility.filter((row) => row.facility_id === dc));
}

function renderDocks(data, dc, shift, names) {
  const steps = dwellSteps(data, dc, shift);
  const lineCaption = document.querySelector("#lineCaption");
  if (lineCaption) {
    lineCaption.textContent = `Average dwell by station for ${placeLabel(dc, shift, names)}.`;
  }
  const localMax = Math.max(...steps.map((s) => Math.max(s.baseline_avg, s.pilot_avg)), 1);
  $("#docks").innerHTML = steps
    .map((s) => {
      const hot = s.step_id === "pick";
      return `<article class="dock ${hot ? "hot" : ""}">
        <div class="lintel"></div>
        <div class="seq">${String(s.step_seq).padStart(2, "0")}</div>
        <div class="name">${s.step_name}</div>
        <div class="bars">
          <div class="bar" title="Baseline"><i style="height:${Math.max(6, (s.baseline_avg / localMax) * 100)}%"></i></div>
          <div class="bar pilot" title="Pilot"><i style="height:${Math.max(6, (s.pilot_avg / localMax) * 100)}%"></i></div>
        </div>
        <div class="nums"><span>${fmt(s.baseline_avg, 1)}</span><span>${fmt(s.pilot_avg, 1)}</span></div>
      </article>`;
    })
    .join("");
}

function renderDensity(orders, gate) {
  const base = orders.filter((o) => o.period === "baseline").map((o) => o.mins);
  const pilot = orders.filter((o) => o.period === "pilot").map((o) => o.mins);
  const lo = 30;
  const hi = 260;
  const b = density(base, lo, hi, 28);
  const p = density(pilot, lo, hi, 28);
  const peak = Math.max(...b.map((bin) => bin.y), ...p.map((bin) => bin.y), 1e-9);
  b.forEach((bin) => {
    bin.y /= peak;
  });
  p.forEach((bin) => {
    bin.y /= peak;
  });
  const layout = pathFrom(b, 220, lo, hi);
  const slaX = layout.x(gate);
  const ticks = [40, 80, 120, 160, 200, 240];
  const svg = $("#density");
  svg.innerHTML = `
    <rect x="0" y="0" width="640" height="220" fill="transparent"></rect>
    ${ticks
      .map(
        (t) =>
          `<line x1="${layout.x(t)}" x2="${layout.x(t)}" y1="12" y2="188" stroke="rgba(234,220,198,0.08)"/>
           <text x="${layout.x(t)}" y="210" fill="#cbbba0" font-size="10" font-family="IBM Plex Mono" text-anchor="middle">${t}m</text>`
      )
      .join("")}
    <path d="${pathFrom(b, 220, lo, hi).d}" fill="rgba(138,122,98,0.45)"></path>
    <path d="${pathFrom(p, 220, lo, hi).d}" fill="rgba(227,160,8,0.42)"></path>
    <line x1="${slaX}" x2="${slaX}" y1="8" y2="192" stroke="#eadcc6" stroke-dasharray="3 4"/>
    <text x="${slaX + 6}" y="20" fill="#eadcc6" font-size="10" font-family="IBM Plex Mono">GATE ${gate}</text>
  `;
}

function renderTape(data, dc, shift, names) {
  const gate = data.sla_minutes;
  const tapeCaption = document.querySelector("#tapeCaption");
  if (tapeCaption) {
    tapeCaption.textContent =
      `${placeLabel(dc, shift, names)} median by week. The scale is fixed at 60–160 minutes. Cutover week of 3–9 Mar is not in the sample.`;
  }
  let series;
  if (dc !== "all" && shift !== "all") {
    series = data.weekly_cell.filter((r) => r.facility_id === dc && r.shift === shift);
  } else if (shift !== "all") {
    series = data.weekly_shift.filter((r) => r.shift === shift);
  } else if (dc !== "all") {
    series = data.weekly_trend.filter((r) => r.facility_id === dc);
  } else {
    series = data.weekly_network;
  }
  const grouped = {};
  series.forEach((r) => {
    const key = r.week_start;
    if (!grouped[key]) grouped[key] = { week: key, baseline: null, pilot: null };
    grouped[key][r.period] = r.median_cycle;
  });
  const weeks = Object.values(grouped).sort((a, b) => a.week.localeCompare(b.week));
  const svg = $("#weekTape");
  if (!weeks.length) {
    svg.innerHTML = "";
    return;
  }
  const left = 40,
    top = 16,
    right = 12,
    bottom = 36;
  const w = 640,
    h = 220;
  const xs = weeks.map((_, i) => left + (i * (w - left - right)) / Math.max(weeks.length - 1, 1));
  const ys = (v) => {
    const lo = 60,
      hi = 160;
    return top + ((hi - v) / (hi - lo)) * (h - top - bottom);
  };
  const line = (key, color) => {
    const pts = weeks
      .map((wk, i) => (wk[key] == null ? null : `${xs[i]},${ys(wk[key])}`))
      .filter(Boolean);
    return `<polyline fill="none" stroke="${color}" stroke-width="2.4" points="${pts.join(" ")}"></polyline>`;
  };
  svg.innerHTML = `
    <line x1="${left}" x2="${w - right}" y1="${ys(gate)}" y2="${ys(gate)}" stroke="rgba(234,220,198,0.25)" stroke-dasharray="4 5"/>
    ${line("baseline", "#8a7a62")}
    ${line("pilot", "#e3a008")}
    ${weeks
      .map((wk, i) =>
        i % 2 === 0
          ? `<text x="${xs[i]}" y="208" fill="#cbbba0" font-size="9" font-family="IBM Plex Mono" text-anchor="middle">${wk.week.slice(5, 10)}</text>`
          : ""
      )
      .join("")}
    <text x="${left}" y="14" fill="#cbbba0" font-size="10" font-family="IBM Plex Mono">${gate} MIN GATE</text>
  `;
}

function renderYards(data, names) {
  const shifts = ["Days", "Swing", "Night"];
  const ids = (data.facilities || []).map((row) => row.facility_id);
  $("#yards").innerHTML = ids
    .map((dc) => {
      const bays = shifts
        .map((shift) => {
          const b = data.facility_shift.find(
            (r) => r.facility_id === dc && r.shift === shift && r.period === "baseline"
          );
          const p = data.facility_shift.find(
            (r) => r.facility_id === dc && r.shift === shift && r.period === "pilot"
          );
          const pain = dc === "FNT-12" && shift === "Night";
          return `<div class="bay ${pain ? "pain" : ""}">
            <div class="shift">${shift}</div>
            <div class="stat">${p ? Math.round(p.median_cycle) : "–"}</div>
            <div class="was">was ${b ? Math.round(b.median_cycle) : "–"} · ${p ? p.sla_miss_pct : "–"}% miss</div>
          </div>`;
        })
        .join("");
      return `<article class="yard">
        <div class="code">${dc}</div>
        <h3>${names[dc]}</h3>
        <div class="bays">${bays}</div>
      </article>`;
    })
    .join("");
}

function renderBoard(orders, gate) {
  const pilot = orders
    .filter((o) => o.period === "pilot")
    .sort((a, b) => b.miss - a.miss || b.mins - a.mins)
    .slice(0, 16);
  const overGate = pilot.filter((o) => o.miss).length;
  const boardCaption = document.querySelector("#boardCaption");
  if (boardCaption) {
    boardCaption.textContent =
      `Longest pilot cartons in this cut. ${overGate} of these ${pilot.length} are over the ${gate}-minute gate.`;
  }
  $("#fids").innerHTML = `
    <div class="head">
      <span>Carton</span><span>Building</span><span>Shift</span><span>Lines</span><span>Min</span><span>Channel</span><span>Remark</span>
    </div>
    ${pilot
      .map((o) => {
        const remark = o.miss ? "HOLD TRAILER" : o.rw ? "REWORK LANE" : "CLEAR";
        return `<div class="row ${o.miss ? "miss" : "hit"}">
          <span>${o.id}</span>
          <span>${o.dc}</span>
          <span>${o.shift}</span>
          <span>${o.lines}</span>
          <span>${fmt(o.mins, 1)}</span>
          <span>${o.ch}</span>
          <span class="remark">${remark}</span>
        </div>`;
      })
      .join("")}
  `;
}

function renderBrief(data) {
  $("#brief").innerHTML = data.brief.map((p) => `<p>${p}</p>`).join("");
  const tbody = $("#tariff tbody");
  tbody.innerHTML = data.sensitivity
    .map((r) => {
      const cartons =
        r.basis === "observed"
          ? `${Number(r.monthly_orders).toLocaleString()} observed`
          : Number(r.monthly_orders).toLocaleString();
      return `<tr>
        <td>${cartons}</td>
        <td>${r.hours_month.toLocaleString()}</td>
        <td>${money(r.usd_month)}</td>
        <td>${r.payback_months.toFixed(1)} mo</td>
      </tr>`;
    })
    .join("");
  const matchedBase = data.money.volume_matched_baseline_usd;
  const matchedPilot = data.money.volume_matched_pilot_usd;
  $("#moneyFoot").textContent =
    `In-window touch labor is ${money(data.money.window_usd)} lower at facility rates, and the pilot also handled more cartons. The same per-carton cut is ${money(matchedBase)} at baseline volume and ${money(matchedPilot)} at pilot volume. The $${data.money.blended_labor_rate}/hr blend is descriptive only. Implementation ${money(data.implementation_cost)} is an input. Payback at observed volume is ${Number(data.money.payback_months_observed).toFixed(1)} months. Other carton counts in the table are scenarios. Bootstrap median drop ${data.tests.bootstrap.ci95_low}–${data.tests.bootstrap.ci95_high} min.`;
}

function paint(data) {
  const dc = document.querySelector("select[name=dc]").value;
  const shift = document.querySelector("select[name=shift]").value;
  const names = namesById(data);
  const orders = filterOrders(data, dc, shift);
  const slaPill = document.querySelector("#slaPill");
  if (slaPill) slaPill.textContent = `SLA ${data.sla_minutes} min`;
  renderTickets(data, orders);
  renderDocks(data, dc, shift, names);
  renderDensity(orders, data.sla_minutes);
  renderTape(data, dc, shift, names);
  renderYards(data, names);
  renderBoard(orders, data.sla_minutes);
  renderBrief(data);
}

async function boot() {
  const data = await fetch("metrics.json", { cache: "no-store" }).then((r) => r.json());
  $("#filters").addEventListener("change", () => paint(data));
  paint(data);
  const shot = new URLSearchParams(location.search).get("shot");
  if (shot) document.body.dataset.shot = shot;
}

boot();
