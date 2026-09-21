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
  const max = Math.max(...counts, 1);
  return counts.map((c, i) => ({
    x0: lo + i * width,
    x1: lo + (i + 1) * width,
    y: c / max,
  }));
}

function pathFrom(bins, h, flip = false) {
  const w = 640;
  const left = 36;
  const right = 16;
  const top = 12;
  const bottom = 32;
  const innerW = w - left - right;
  const innerH = h - top - bottom;
  const x = (v) => left + ((v - 30) / (220 - 30)) * innerW;
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
      cls: "good",
    },
    {
      k: "Same-day miss",
      v: `${missP.toFixed(1)}<em>%</em>`,
      h: `Was ${missB.toFixed(1)}% of cartons past 120 min`,
      cls: missP < 10 ? "good" : "alert",
    },
    {
      k: "P90 dwell",
      v: `${Math.round(p90P)}<em>min</em>`,
      h: `Tail compressed from ${Math.round(p90B)} min`,
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

function renderDocks(data, dc) {
  const max = Math.max(...data.step_profile.map((s) => s.baseline_avg));
  const steps =
    dc === "all"
      ? data.step_profile
      : data.step_profile.map((s) => {
          const b = data.step_by_facility.find(
            (r) => r.facility_id === dc && r.period === "baseline" && r.step_id === s.step_id
          );
          const p = data.step_by_facility.find(
            (r) => r.facility_id === dc && r.period === "pilot" && r.step_id === s.step_id
          );
          return {
            ...s,
            baseline_avg: b ? b.avg_dwell : s.baseline_avg,
            pilot_avg: p ? p.avg_dwell : s.pilot_avg,
          };
        });
  const localMax = Math.max(...steps.map((s) => Math.max(s.baseline_avg, s.pilot_avg)), max);
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

function renderDensity(orders) {
  const base = orders.filter((o) => o.period === "baseline").map((o) => o.mins);
  const pilot = orders.filter((o) => o.period === "pilot").map((o) => o.mins);
  const b = density(base, 30, 220, 28);
  const p = density(pilot, 30, 220, 28);
  const layout = pathFrom(b, 220);
  const slaX = layout.x(120);
  const ticks = [40, 80, 120, 160, 200];
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
    <path d="${pathFrom(b, 220).d}" fill="rgba(138,122,98,0.45)"></path>
    <path d="${pathFrom(p, 220).d}" fill="rgba(227,160,8,0.42)"></path>
    <line x1="${slaX}" x2="${slaX}" y1="8" y2="192" stroke="#eadcc6" stroke-dasharray="3 4"/>
    <text x="${slaX + 6}" y="20" fill="#eadcc6" font-size="10" font-family="IBM Plex Mono">GATE 120</text>
  `;
}

function renderTape(data, dc) {
  const series =
    dc === "all"
      ? data.weekly_network
      : data.weekly_trend.filter((r) => r.facility_id === dc);
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
    <line x1="${left}" x2="${w - right}" y1="${ys(120)}" y2="${ys(120)}" stroke="rgba(234,220,198,0.25)" stroke-dasharray="4 5"/>
    ${line("baseline", "#8a7a62")}
    ${line("pilot", "#e3a008")}
    ${weeks
      .map((wk, i) =>
        i % 2 === 0
          ? `<text x="${xs[i]}" y="208" fill="#cbbba0" font-size="9" font-family="IBM Plex Mono" text-anchor="middle">${wk.week.slice(5, 10)}</text>`
          : ""
      )
      .join("")}
    <text x="${left}" y="14" fill="#cbbba0" font-size="10" font-family="IBM Plex Mono">120 MIN GATE</text>
  `;
}

function renderYards(data) {
  const names = {
    "AUS-01": "Austin Gateway",
    "EWR-07": "Newark Hub",
    "FNT-12": "Fontana West",
  };
  const shifts = ["Days", "Swing", "Night"];
  $("#yards").innerHTML = Object.keys(names)
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
          const ok = p && p.sla_miss_pct < 8;
          return `<div class="bay ${pain ? "pain" : ok ? "ok" : ""}">
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

function renderBoard(orders) {
  const pilot = orders
    .filter((o) => o.period === "pilot")
    .sort((a, b) => b.miss - a.miss || b.mins - a.mins)
    .slice(0, 16);
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
    .map(
      (r) => `<tr>
        <td>${r.monthly_orders.toLocaleString()}</td>
        <td>${r.hours_month.toLocaleString()}</td>
        <td>${money(r.usd_month)}</td>
        <td>${r.payback_months.toFixed(1)} mo</td>
      </tr>`
    )
    .join("");
  $("#moneyFoot").textContent =
    `Observed eight-week touch labor returned ${money(data.money.window_usd)} at $${data.money.blended_labor_rate}/hr blended. Implementation ${money(data.implementation_cost)}. Mann–Whitney on cycle time p < 0.001; bootstrap median drop ${data.tests.bootstrap.ci95_low}–${data.tests.bootstrap.ci95_high} min.`;
}

function paint(data) {
  const dc = document.querySelector("select[name=dc]").value;
  const shift = document.querySelector("select[name=shift]").value;
  const orders = filterOrders(data, dc, shift);
  renderTickets(data, orders);
  renderDocks(data, dc);
  renderDensity(orders);
  renderTape(data, dc);
  renderYards(data);
  renderBoard(orders);
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
