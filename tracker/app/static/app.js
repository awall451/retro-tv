/* Retro TV channel tracker - front end. Plain JS, no dependencies. */
(() => {
  "use strict";

  const PAGE = 50;
  const S = {
    snap: null, planned: [], requests: [], meta: null,
    watch: null, watchAt: 0, popRange: 7,
    view: "channels", channelNum: null,
    chMode: "tiles",
    lib: {
      tv: { q: "", on: "any", genre: "", decade: "", res: "", chap: "any", sort: "title", dir: 1, page: 0 },
      movies: { q: "", on: "any", genre: "", decade: "", res: "", chap: "any", sort: "title", dir: 1, page: 0 },
    },
    sel: new Map(), // "show:12" -> {type, id, title, on}
    ctxFrom: null,  // channel number the selection was made in (channel detail)
  };
  const byId = { show: new Map(), movie: new Map() };
  let channelsByNum = new Map();

  // ---------- small helpers
  const $ = (s, r = document) => r.querySelector(s);
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    if (attrs) for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (k === "checked" || k === "selected" || k === "disabled" || k === "value") el[k] = v;
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const k of kids.flat(Infinity)) {
      if (k == null || k === false) continue;
      el.append(k instanceof Node ? k : document.createTextNode(String(k)));
    }
    return el;
  }
  const fmt = (n, d = 0) => (n == null ? "–" : Number(n).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }));
  const plural = (n, one, many) => `${fmt(n)} ${n === 1 ? one : many || one + "s"}`;
  const pct = (a, b) => (b ? Math.round((100 * a) / b) : 0);
  const store = {
    get(k, d) { try { const v = localStorage.getItem("rtt." + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem("rtt." + k, JSON.stringify(v)); } catch { /* ignore */ } },
  };
  function when(iso) {
    if (!iso) return "–";
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  }
  function toast(msg, err) {
    const t = $("#toast");
    t.textContent = msg; t.className = "toast" + (err ? " err" : ""); t.hidden = false;
    clearTimeout(toast.t); toast.t = setTimeout(() => (t.hidden = true), err ? 6000 : 3000);
  }
  async function api(method, path, body) {
    const opt = { method, headers: {} };
    if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
    const r = await fetch(path, opt);
    let data = null;
    try { data = await r.json(); } catch { /* empty */ }
    if (!r.ok) throw new Error((data && data.error) || `HTTP ${r.status}`);
    return data;
  }
  function bar(value, max, alt) {
    const i = h("i"); i.style.width = `${Math.min(100, pct(value, max))}%`;
    return h("div", { class: "bar" + (alt ? " alt" : ""), role: "img", "aria-label": `${value} of ${max}` }, i);
  }
  // A mirror (an HD twin) has no schedule of its own: a change to it is a
  // change to the channel it mirrors (the server maps it the same way).
  function srcNum(num) {
    const c = channelsByNum.get(String(num));
    return c && c.mirrorOf != null ? String(c.mirrorOf) : String(num);
  }
  function chChip(num) {
    const c = channelsByNum.get(String(num));
    return h("a", { class: "chip", href: `#channel/${encodeURIComponent(num)}`, title: c ? c.name : "" }, num);
  }

  // ---------- theme
  const THEMES = ["auto", "light", "dark"];
  function applyTheme(t) {
    if (t === "auto") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", t);
    $("#themeLabel").textContent = t[0].toUpperCase() + t.slice(1);
  }
  let theme = store.get("theme", "auto");
  if (!THEMES.includes(theme)) theme = "auto";
  applyTheme(theme);
  $("#themeBtn").addEventListener("click", () => {
    theme = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
    store.set("theme", theme); applyTheme(theme);
  });

  // ---------- data
  async function loadSnapshot() {
    try {
      S.snap = await api("GET", "/api/snapshot");
    } catch (e) {
      S.snap = null;
      $("#snapinfo").textContent = "No snapshot yet";
      return;
    }
    byId.show.clear(); byId.movie.clear();
    for (const s of S.snap.library.shows) byId.show.set(s.id, s);
    for (const m of S.snap.library.movies) byId.movie.set(m.id, m);
    channelsByNum = new Map(S.snap.channels.map((c) => [String(c.number), c]));
    const L = S.snap.library;
    $("#snapinfo").textContent = `${S.snap.channels.length} channels · ${fmt(L.shows.length)} shows · ${fmt(L.movies.length)} films · snapshot ${when(S.snap.generatedAt)}`;
  }
  async function loadQueue() {
    const [reqs, planned] = await Promise.all([api("GET", "/api/requests"), api("GET", "/api/planned")]);
    S.requests = reqs; S.planned = planned;
    const n = reqs.filter((r) => r.status === "pending").length;
    const b = $("#pendingBadge"); b.textContent = n; b.hidden = n === 0;
  }

  // ---------- routing
  function route() {
    const hash = decodeURIComponent(location.hash.replace(/^#/, "")) || "channels";
    const [v, arg] = hash.split("/");
    S.view = ["channels", "channel", "tv", "movies", "queue", "popular"].includes(v) ? v : "channels";
    S.channelNum = v === "channel" ? arg : null;
    for (const a of document.querySelectorAll(".tabs a")) {
      const on = a.dataset.view === (S.view === "channel" ? "channels" : S.view);
      a.classList.toggle("active", on);
      if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    }
    render();
    if ((S.view === "popular" || S.view === "channel") && Date.now() - S.watchAt > 30000) loadWatch();
  }
  window.addEventListener("hashchange", () => { route(); window.scrollTo(0, 0); });

  function render() {
    const main = $("#main");
    main.replaceChildren();
    if (!S.snap && S.view !== "queue") {
      main.append(h("div", { class: "card empty" },
        h("h3", { text: "No snapshot yet" }),
        h("p", { text: "Run generator/make_snapshot.py on the workstation to upload one. The queue still works." })));
      updateBar();
      return;
    }
    if (S.view === "channels") renderChannels(main);
    else if (S.view === "channel") renderChannel(main, S.channelNum);
    else if (S.view === "tv") renderLibrary(main, "tv");
    else if (S.view === "movies") renderLibrary(main, "movies");
    else if (S.view === "popular") renderPopular(main);
    else renderQueue(main);
    updateBar();
  }

  // ---------- channels
  function plannedTargets(pid) {
    return S.requests.filter((r) => r.status === "pending" && ((r.channel && r.channel.planned === pid) || (r.from && r.from.planned === pid))).length;
  }
  function chapterMeters(c) {
    const n = c.counts.items;
    return h("div", { class: "mini" },
      h("div", { class: "meter" }, h("span", { text: "Chapters" }), bar(c.counts.chaptered, n), h("span", { class: "num", text: `${fmt(c.counts.chaptered)}/${fmt(n)}` })),
      h("div", { class: "meter" }, h("span", { text: "Ad breaks" }), bar(c.counts.withBreaks, n, true), h("span", { class: "num", text: `${fmt(c.counts.withBreaks)}/${fmt(n)}` })));
  }
  function statLine(c) {
    const k = c.counts;
    if (c.kind === "movies") return [h("b", { text: plural(k.movies, "film") }), ` · ${fmt(k.hours)} h`];
    if (c.kind === "shows") return [h("b", { text: plural(k.shows, "show") }), ` · ${fmt(k.episodes)} episodes · ${fmt(k.hours)} h`];
    return [h("b", { text: plural(k.items, "item") }), ` · ${fmt(k.hours)} h`];
  }
  function presetText(c) {
    if (!c.presets.length) return "No ads";
    return c.presets.map((p) => `${p.name} (${p.role}${p.pool ? `, ${p.pool.items} clips` : ""})`).join("; ");
  }
  function renderChannels(main) {
    const tb = h("div", { class: "toolbar" },
      h("h2", { text: "Channels" }),
      h("span", { class: "spacer" }),
      h("div", { class: "seg", role: "group", "aria-label": "Layout" },
        h("button", { type: "button", class: S.chMode === "tiles" ? "on" : "", onclick: () => { S.chMode = "tiles"; store.set("chMode", "tiles"); render(); } }, "Tiles"),
        h("button", { type: "button", class: S.chMode === "list" ? "on" : "", onclick: () => { S.chMode = "list"; store.set("chMode", "list"); render(); } }, "List")),
      h("button", { type: "button", class: "btn", onclick: () => { location.hash = "#queue"; setTimeout(() => { const f = $("#planName"); if (f) f.focus(); }, 50); } }, "+ Plan a channel"));
    main.append(tb);
    const chans = S.snap.channels;
    if (S.chMode === "tiles") {
      const grid = h("div", { class: "tiles" });
      for (const c of chans) {
        grid.append(h("a", { class: "tile", href: `#channel/${encodeURIComponent(c.number)}` },
          h("div", { class: "tile-head" }, h("span", { class: "chnum", text: c.number }), h("span", { class: "tile-name", text: c.name })),
          h("div", { class: "tile-stats" }, statLine(c)),
          h("div", { class: "kv" }, "Order: ", h("b", { text: c.order || "–" })),
          h("div", { class: "kv" }, "Ads: ", h("b", { text: presetText(c) })),
          chapterMeters(c),
          h("div", { class: "tile-foot" }, h("span", { class: `pill ${c.kind}`, text: c.kind }),
            c.enabled ? null : h("span", { class: "pill rejected", text: "disabled" }))));
      }
      for (const p of S.planned) grid.append(plannedTile(p));
      main.append(grid);
    } else {
      const list = h("div", { class: "chlist" },
        h("div", { class: "chrow head" }, h("span", { text: "No." }), h("span", { text: "Name" }), h("span", { class: "opt", text: "Kind" }),
          h("span", { class: "opt", text: "Size" }), h("span", { class: "opt", text: "Chapters" }), h("span", { text: "Ad breaks" })));
      for (const c of chans) {
        const n = c.counts.items;
        list.append(h("a", { class: "chrow", href: `#channel/${encodeURIComponent(c.number)}` },
          h("span", { class: "chnum", text: c.number }),
          h("span", {}, h("b", { text: c.name }), h("div", { class: "muted small", text: c.order || "" })),
          h("span", { class: "opt" }, h("span", { class: `pill ${c.kind}`, text: c.kind })),
          h("span", { class: "opt small muted" }, statLine(c)),
          h("span", { class: "opt small num", text: `${fmt(c.counts.chaptered)}/${fmt(n)} (${pct(c.counts.chaptered, n)}%)` }),
          h("span", { class: "small num", text: `${fmt(c.counts.withBreaks)}/${fmt(n)} (${pct(c.counts.withBreaks, n)}%)` })));
      }
      for (const p of S.planned) {
        list.append(h("div", { class: "chrow" },
          h("span", { class: "chnum", text: p.number || "?" }),
          h("span", {}, h("b", { text: p.name }), " ", h("span", { class: "pill planned", text: "planned" })),
          h("span", { class: "opt" }, p.kind ? h("span", { class: `pill ${p.kind}`, text: p.kind }) : null),
          h("span", { class: "opt small muted", text: p.note || "" }), h("span", { class: "opt" }), h("span", {})));
      }
      main.append(list);
    }
  }
  function plannedTile(p) {
    const n = plannedTargets(p.id);
    return h("div", { class: "tile planned" },
      h("div", { class: "tile-head" }, h("span", { class: "chnum", text: p.number || "?" }), h("span", { class: "tile-name", text: p.name })),
      h("div", { class: "tile-stats" }, "Planned channel", p.kind ? ` · ${p.kind}` : "", n ? ` · ${plural(n, "pending request")}` : ""),
      p.note ? h("div", { class: "kv", text: p.note }) : null,
      h("div", { class: "tile-foot" }, h("span", { class: "pill planned", text: "planned" }), h("span", { class: "spacer" }),
        h("button", { type: "button", class: "btn small danger", onclick: () => deletePlanned(p) }, "Delete")));
  }

  function renderChannel(main, num) {
    const c = channelsByNum.get(String(num));
    main.append(h("div", { class: "crumbs" }, h("a", { href: "#channels", text: "← All channels" })));
    if (!c) { main.append(h("div", { class: "card empty", text: `No channel ${num} in the snapshot.` })); return; }
    const k = c.counts;
    main.append(h("div", { class: "detail-head" },
      h("span", { class: "chnum", text: c.number }),
      h("div", {}, h("h2", { text: c.name }), h("div", { class: "muted small" }, statLine(c)),
        h("div", { class: "tile-foot" }, h("span", { class: `pill ${c.kind}`, text: c.kind }),
          h("span", { class: "pill", text: `membership: ${c.membership}` })))));
    const facts = h("div", { class: "facts" },
      fact("Playback order", c.order || "–"),
      fact("Ads / filler", presetText(c)),
      fact("Chapters", `${fmt(k.chaptered)} of ${fmt(k.items)} ${c.kind === "movies" ? "films" : "episodes"} (${pct(k.chaptered, k.items)}%)`),
      fact("Qualifying ad breaks", `${fmt(k.breaks)} breaks in ${fmt(k.withBreaks)} ${c.kind === "movies" ? "films" : "episodes"}`),
      fact("FFmpeg profile", c.profile || "–"),
      watchFact(c.number),
      c.check ? fact("Playout check", c.check.outsideMembers ? `${c.check.outsideMembers} of ${c.check.playoutItems} scheduled items are outside the resolved members` : `All ${c.check.playoutItems} scheduled items are members`) : null);
    main.append(facts);
    for (const col of c.collections || []) {
      main.append(h("details", { class: "query" }, h("summary", {}, `Smart collection: ${col.name} (mode ${col.mode})`), h("code", { text: col.query })));
    }
    for (const p of c.presets) {
      if (p.expression) main.append(h("p", { class: "small muted" }, `${p.name}: ${p.kind}, ${p.mode}${p.padToMinutes ? ` to ${p.padToMinutes} min` : ""}, rule `, h("code", { text: p.expression })));
    }
    if (c.notes && c.notes.length) main.append(h("p", { class: "small muted", text: "Notes: " + c.notes.join("; ") }));

    S.ctxFrom = c.number;
    const isShow = c.kind !== "movies";
    const members = c.members;
    const allBox = h("input", { type: "checkbox", "aria-label": "Select all members", onchange: (e) => {
      for (const m of members) toggleSel(m.type, m.id, e.target.checked, false);
      render();
    } });
    allBox.checked = members.length > 0 && members.every((m) => S.sel.has(`${m.type}:${m.id}`));
    const rows = h("div", { class: "rows" });
    if (members.some((m) => m.type === "show")) {
      rows.append(h("div", { class: "row head cols-mshow" }, h("span", {}, allBox), h("span", { text: "Show" }), h("span", { class: "c", text: "Episodes" }),
        h("span", { class: "c", text: "Seasons" }), h("span", { class: "c", text: "Hours" }), h("span", { class: "c", text: "Res" }), h("span", { text: "Chapters / ad breaks" })));
    } else {
      rows.append(h("div", { class: "row head cols-mmov" }, h("span", {}, allBox), h("span", { text: "Film" }), h("span", { class: "c", text: "Runtime" }),
        h("span", { class: "c", text: "Year" }), h("span", { class: "c", text: "Res" }), h("span", { text: "Chapters / ad breaks" })));
    }
    for (const m of members) {
      const key = `${m.type}:${m.id}`;
      const cb = h("input", { type: "checkbox", "aria-label": `Select ${m.t}`, checked: S.sel.has(key), onchange: (e) => {
        toggleSel(m.type, m.id, e.target.checked, false); e.target.closest(".row").classList.toggle("sel", e.target.checked); updateBar();
      } });
      if (m.type === "show") {
        const s = byId.show.get(m.id) || {};
        rows.append(h("div", { class: "row cols-mshow" + (S.sel.has(key) ? " sel" : "") },
          h("span", { class: "cb" }, cb),
          h("span", { class: "title wide" }, m.t, h("div", { class: "sub", text: [s.y, (s.g || []).slice(0, 3).join(", ")].filter(Boolean).join(" · ") })),
          h("span", { class: "facts-line" },
            h("span", { class: "c" }, fmt(m.n), h("span", { class: "lbl", text: " eps" })),
            h("span", { class: "c" }, fmt(m.se), h("span", { class: "lbl", text: m.se === 1 ? " season" : " seasons" })),
            h("span", { class: "c" }, fmt(m.h, 1), h("span", { class: "lbl", text: " h" })),
            h("span", { class: "c" }, m.q),
            h("span", { class: "c small" }, `ch ${fmt(m.ch)}/${fmt(m.n)} · breaks ${fmt(m.bre)}/${fmt(m.n)}`))));
      } else {
        rows.append(h("div", { class: "row cols-mmov" + (S.sel.has(key) ? " sel" : "") },
          h("span", { class: "cb" }, cb),
          h("span", { class: "title wide" }, m.t),
          h("span", { class: "facts-line" },
            h("span", { class: "c" }, `${fmt(m.m)} min`),
            h("span", { class: "c" }, m.y || "–"),
            h("span", { class: "c" }, m.q),
            h("span", { class: "c small" }, `${plural(m.ch, "chapter")} · ${plural(m.br, "break")}`))));
      }
    }
    if (!members.length) rows.append(h("div", { class: "empty", text: "No members." }));
    main.append(h("div", { class: "toolbar" }, h("h3", { text: `Members (${fmt(members.length)})` }), h("span", { class: "spacer" }),
      h("span", { class: "small muted", text: isShow ? "Counts are for the episodes this channel plays." : "" })), rows);
  }
  function fact(k, v) { return h("div", { class: "fact" }, h("div", { class: "k", text: k }), h("div", { class: "v", text: v })); }

  // ---------- popularity (watch minutes)
  async function loadWatch() {
    try {
      S.watch = await api("GET", "/api/watch?days=30");
      S.watchAt = Date.now();
    } catch (e) { S.watch = null; }
    if (S.view === "popular" || S.view === "channel") render();
  }
  function dur(sec) {
    const m = Math.round((sec || 0) / 60);
    if (m < 60) return `${fmt(m)} min`;
    return `${fmt(Math.floor(m / 60))} h ${m % 60 ? `${m % 60} min` : ""}`.trim();
  }
  function dayList(n) {
    const out = [];
    const t = Date.parse(S.watch.today + "T12:00:00Z");
    for (let i = n - 1; i >= 0; i--) out.push(new Date(t - i * 864e5).toISOString().slice(0, 10));
    return out;
  }
  // An HD twin: a channel in group HD at another channel's number + the offset (100 in the viewer).
  function isTwin(num) {
    const n = Number(num), c = channelsByNum.get(String(num));
    if (!Number.isInteger(n) || !c || String(c.group || "").toUpperCase() !== "HD") return false;
    const offsets = (S.watch && S.watch.rules && S.watch.rules.hdOffsets) || [100];
    return offsets.some((o) => n > o && channelsByNum.has(String(n - o)));
  }
  function aggregate(n) {
    const per = new Map(), hours = new Array(24).fill(0), devs = {};
    let total = 0, hd = 0, away = 0;
    for (const d of dayList(n)) {
      const day = S.watch.days[d] || {};
      for (const [ch, r] of Object.entries(day)) {
        const a = per.get(ch) || { ch, s: 0, hd: 0, dev: {} };
        a.s += r.s; a.hd += r.hd; total += r.s; hd += r.hd; away += r.u || 0;
        for (const [k, v] of Object.entries(r.dev)) { a.dev[k] = (a.dev[k] || 0) + v; devs[k] = (devs[k] || 0) + v; }
        r.h.forEach((v, i) => (hours[i] += v));
        per.set(ch, a);
      }
    }
    return { per, rows: [...per.values()].filter((a) => a.s > 0).sort((a, b) => b.s - a.s), hours, devs, total, hd, away };
  }
  function daily(ch, n) { return dayList(n).map((d) => [d, ((S.watch.days[d] || {})[ch] || {}).s || 0]); }
  // Device colours: fixed per label, never by rank. Labels named in TRACKER_DEVICES (or
  // TRACKER_TV_LABEL) take the free colours in alphabetical order; past two, grey.
  const DEV_FIXED = { "browser (desktop)": 1, "browser (mobile)": 2, "browser (tv)": 3, direct: 5 };
  const DEV_FREE = [0, 4];
  function devLabels() {
    const all = new Set();
    for (const day of Object.values((S.watch && S.watch.days) || {}))
      for (const r of Object.values(day)) for (const k of Object.keys(r.dev || {})) all.add(k);
    for (const x of (S.watch && S.watch.live) || []) for (const k of x.devices) all.add(k);
    return [...all].filter((k) => !(k in DEV_FIXED)).sort((a, b) => a.localeCompare(b));
  }
  const devClass = (k) => {
    if (k in DEV_FIXED) return `dev-${DEV_FIXED[k]}`;
    const i = devLabels().indexOf(k);
    return i >= 0 && i < DEV_FREE.length ? `dev-${DEV_FREE[i]}` : "dev-x";
  };
  const devName = (k) => (k === "direct" ? "direct (Roku, Kodi, other players)" : k);
  const devRank = (k) => (k === "direct" ? 3 : k.startsWith("browser") ? 2 : 1);
  const devSort = (a, b) => devRank(a) - devRank(b) || a.localeCompare(b);
  function stack(dev, total, label) {
    const el = h("div", { class: "stack", role: "img", "aria-label": label || "Device split" });
    for (const k of Object.keys(dev).sort(devSort)) {
      if (!dev[k]) continue;
      const i = h("i", { class: devClass(k), title: `${devName(k)}: ${dur(dev[k])} (${pct(dev[k], total)}%)` });
      i.style.flexGrow = String(dev[k]);
      el.append(i);
    }
    return el;
  }
  const SVGNS = "http://www.w3.org/2000/svg";
  function svg(tag, attrs, ...kids) {
    const el = document.createElementNS(SVGNS, tag);
    for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
    for (const k of kids) el.append(k);
    return el;
  }
  function spark(series, cls) {
    const max = Math.max(1, ...series.map((x) => x[1]));
    const w = series.length * 4;
    const s = svg("svg", { class: "spark " + (cls || ""), viewBox: `0 0 ${w} 24`, preserveAspectRatio: "none",
      role: "img", "aria-label": `Daily watch time, last ${series.length} days` });
    s.append(svg("line", { x1: 0, x2: w, y1: 23.5, y2: 23.5, class: "base" }));
    series.forEach(([d, v], i) => {
      const hgt = v ? Math.max(2, (22 * v) / max) : 0;
      const r = svg("rect", { x: i * 4 + 0.5, y: 24 - hgt, width: 3, height: hgt, rx: 1 });
      r.append(svg("title", {}, `${d}: ${dur(v)}`));
      s.append(r);
    });
    return s;
  }
  function watchFact(num) {
    if (!S.watch) return null;
    const by = (n) => aggregate(n).per.get(String(num));
    const t = by(1), w = by(7), m = by(30);
    const box = h("div", { class: "fact" }, h("div", { class: "k", text: "Watched" }),
      h("div", { class: "v", text: `${dur(t && t.s)} today · ${dur(w && w.s)} in 7 days · ${dur(m && m.s)} in 30 days` }));
    if (m && m.s) box.append(spark(daily(String(num), 30), "wide"));
    return box;
  }
  function renderPopular(main) {
    const W = S.watch;
    const n = S.popRange;
    const seg = h("div", { class: "seg", role: "group", "aria-label": "Range" },
      [[1, "Today"], [7, "7 days"], [30, "30 days"]].map(([v, t]) => h("button", { type: "button", class: n === v ? "on" : "",
        "aria-pressed": n === v ? "true" : "false", onclick: () => { S.popRange = v; store.set("popRange", v); render(); } }, t)));
    main.append(h("div", { class: "toolbar" }, h("h2", { text: "Popular" }), seg, h("span", { class: "spacer" }),
      W ? h("span", { class: "small muted", text: `Tracking since ${W.since || W.today} · ${W.poller.enabled ? (W.poller.lastError ? "ErsatzTV poll failing" : `ErsatzTV polled ${when(W.poller.lastPoll)}`) : "ErsatzTV poller off"}` }) : null));
    if (!W) { main.append(h("div", { class: "card empty", text: "No watch data yet." })); return; }
    const A = aggregate(n);
    const live = h("div", { class: "live" }, h("b", { text: "On now: " }),
      W.live.length ? W.live.map((x) => h("span", { class: "live-item" }, chChip(x.channel),
        h("span", { class: "small muted", text: " " + x.devices.map(devName).join(", ") }))) : h("span", { class: "muted", text: "nothing is being watched" }));
    main.append(live);
    const top = A.rows[0];
    main.append(h("div", { class: "facts" },
      bigFact("Watch time", dur(A.total)),
      bigFact("Channels watched", fmt(A.rows.length)),
      bigFact("Most watched", top ? `${top.ch} ${(channelsByNum.get(top.ch) || {}).name || ""}` : "–"),
      bigFact("HD share", A.total ? `${pct(A.hd, A.total)}%` : "–")));
    // Left on with nobody at the controls: past the viewer's sleep time. Not watch time.
    if (A.away) main.append(h("p", { class: "small muted", title: "Minutes a viewer kept playing with no key press past its sleep time (the viewer's sleep timer, or the tracker's WATCH_IDLE_MIN). Not counted as watch time or in the rankings.",
      text: `Unattended (left on, nobody at the controls): ${dur(A.away)}, not counted above.` }));

    const maxS = top ? top.s : 1;
    const list = h("div", { class: "rows poprows" },
      h("div", { class: "row head cols-pop" }, h("span", { text: "#" }), h("span", { text: "Channel" }), h("span", { text: "Watch time" }),
        h("span", { text: "Last 30 days" }), h("span", { text: "Devices" })));
    A.rows.slice(0, 25).forEach((a, i) => {
      const c = channelsByNum.get(a.ch);
      list.append(h("a", { class: "row cols-pop", href: `#channel/${encodeURIComponent(a.ch)}` },
        h("span", { class: "rank num", text: String(i + 1) }),
        h("span", { class: "title" }, h("span", { class: "chip", text: a.ch }), " ", c ? c.name : "",
          a.hd ? h("span", { class: "sub", text: ` HD ${pct(a.hd, a.s)}%` }) : null),
        h("span", { class: "popbar" }, bar(a.s, maxS), h("span", { class: "num small", text: dur(a.s) })),
        h("span", {}, spark(daily(a.ch, 30))),
        h("span", {}, stack(a.dev, a.s, `Devices for channel ${a.ch}`))));
    });
    if (!A.rows.length) list.append(h("div", { class: "empty", text: n === 1 ? "Nothing watched today yet." : "Nothing watched in this range." }));

    const maxH = Math.max(1, ...A.hours);
    const peak = A.hours.indexOf(Math.max(...A.hours));
    const hours = h("div", { class: "hours", role: "img", "aria-label": "Watch time by hour of day" },
      A.hours.map((v, i) => { const b = h("i", { title: `${String(i).padStart(2, "0")}:00–${String(i + 1).padStart(2, "0")}:00: ${dur(v)}` });
        b.style.height = `${v ? Math.max(3, (100 * v) / maxH) : 0}%`; if (i === peak && v) b.className = "peak"; return b; }));
    const hourAxis = h("div", { class: "hours-axis small muted" }, ["0", "6", "12", "18", "24"].map((t) => h("span", { text: t })));
    const devKeys = Object.keys(A.devs).sort(devSort);
    const devCard = h("div", { class: "card" }, h("h3", { text: "Devices" }),
      A.total ? stack(A.devs, A.total, "Watch time by device") : h("p", { class: "muted", text: "No data." }),
      h("table", { class: "devtable small" }, devKeys.map((k) => h("tr", {},
        h("td", {}, h("i", { class: "sw " + devClass(k) }), devName(k)), h("td", { class: "num", text: dur(A.devs[k]) }),
        h("td", { class: "num muted", text: `${pct(A.devs[k], A.total)}%` })))),
      h("p", { class: "small muted", text: "Browser viewers (and the Retro TV box) report themselves; whatever plays ErsatzTV directly (Roku, Kodi) is seen only as a running channel and counts once, as direct." }));
    const right = h("div", {},
      h("div", { class: "card" }, h("h3", { text: "Peak hours" }), hours, hourAxis,
        h("p", { class: "small muted", text: A.total ? `Busiest: ${String(peak).padStart(2, "0")}:00–${String(peak + 1).padStart(2, "0")}:00 (${W.tz})` : "No data." })),
      devCard);
    main.append(h("div", { class: "qgrid" }, h("div", {}, h("h3", { class: "sect", text: "Top channels" }), list), right));

    const watched30 = aggregate(30).per;
    const never = S.snap.channels.filter((c) => !isTwin(c.number) && !(watched30.get(String(c.number)) || {}).s);
    main.append(h("div", { class: "card never" }, h("h3", {}, "Not watched in 30 days ", h("span", { class: "pill", text: String(never.length) })),
      W.since && W.since > dayList(30)[0] ? h("p", { class: "small muted", text: `Tracking started ${W.since}, so this covers less than 30 days.` }) : null,
      h("div", { class: "chans" }, never.map((c) => chChip(c.number)))));
  }
  function bigFact(k, v) { return h("div", { class: "fact" }, h("div", { class: "k", text: k }), h("div", { class: "v big", text: v })); }

  // ---------- library
  function decadeOf(y) { return y ? `${Math.floor(y / 10) * 10}s` : ""; }
  function libItems(kind) { return kind === "tv" ? S.snap.library.shows : S.snap.library.movies; }
  function filtered(kind) {
    const f = S.lib[kind];
    const q = f.q.trim().toLowerCase();
    let items = libItems(kind).filter((x) => {
      if (q) {
        const hay = (x.t + " " + (x.d || []).join(" ") + " " + (x.studio || []).join(" ") + " " + (x.f || "")).toLowerCase();
        if (!q.split(/\s+/).every((w) => hay.includes(w))) return false;
      }
      if (f.on === "none" && x.on.length) return false;
      if (f.on === "some" && !x.on.length) return false;
      if (!["any", "none", "some"].includes(f.on) && !x.on.includes(f.on)) return false;
      if (f.genre && !(x.g || []).includes(f.genre)) return false;
      if (f.decade && decadeOf(x.y) !== f.decade) return false;
      if (f.res && x.q !== f.res) return false;
      if (f.chap === "yes" && !(kind === "tv" ? x.ch > 0 : x.ch >= 2)) return false;
      if (f.chap === "breaks" && !(kind === "tv" ? x.bre > 0 : x.br > 0)) return false;
      if (f.chap === "no" && (kind === "tv" ? x.ch > 0 : x.ch >= 2)) return false;
      return true;
    });
    const key = {
      title: (x) => (x.st || x.t).toLowerCase(), year: (x) => x.y || 0, runtime: (x) => x.m || 0, hours: (x) => x.h || 0,
      episodes: (x) => x.n || 0, chapters: (x) => (kind === "tv" ? (x.n ? x.ch / x.n : 0) : x.ch), breaks: (x) => (kind === "tv" ? x.bre : x.br),
      channels: (x) => x.on.length, res: (x) => ({ SD: 1, "720p": 2, "1080p": 3, "4K": 4 }[x.q] || 0),
    }[f.sort] || ((x) => (x.st || x.t).toLowerCase());
    items = items.slice().sort((a, b) => {
      const ka = key(a), kb = key(b);
      if (ka < kb) return -f.dir;
      if (ka > kb) return f.dir;
      return (a.st || a.t).localeCompare(b.st || b.t);
    });
    return items;
  }
  function renderLibrary(main, kind) {
    const f = S.lib[kind];
    const items = libItems(kind);
    const genres = [...new Set(items.flatMap((x) => x.g || []))].sort();
    const decades = [...new Set(items.map((x) => decadeOf(x.y)).filter(Boolean))].sort();
    const save = () => store.set("lib." + kind, { ...f, page: 0, q: "" });
    const set = (k) => (e) => { f[k] = e.target.value; f.page = 0; save(); renderLibraryBody(kind); };
    const sel = (k, opts, label) => h("label", { class: "fld" }, h("span", { text: label }),
      h("select", { onchange: set(k) }, opts.map(([v, t]) => h("option", { value: v, selected: f[k] === v }, t))));
    const search = h("input", { type: "search", placeholder: kind === "tv" ? "Search shows" : "Search films, directors", value: f.q, "aria-label": "Search" });
    let tmr;
    // The box may be gone by the time the timer fires (another page opened): its own
    // library's search is kept, but nothing is drawn into the page now showing.
    search.addEventListener("input", (e) => { clearTimeout(tmr); tmr = setTimeout(() => { f.q = e.target.value; f.page = 0; if (search.isConnected) renderLibraryBody(kind); }, 150); });
    const chOpts = [["any", "Any"], ["some", "On a channel"], ["none", "Not on any channel"], ...S.snap.channels.map((c) => [String(c.number), `${c.number} ${c.name}`])];
    main.append(h("div", { class: "toolbar" },
      h("label", { class: "fld search" }, h("span", { text: kind === "tv" ? "TV library" : "Movie library" }), search),
      sel("on", chOpts, "Channel"),
      sel("genre", [["", "All genres"], ...genres.map((g) => [g, g])], "Genre"),
      sel("decade", [["", "All decades"], ...decades.map((d) => [d, d])], "Decade"),
      sel("res", [["", "Any"], ["SD", "SD"], ["720p", "720p"], ["1080p", "1080p"], ["4K", "4K"]], "Resolution"),
      sel("chap", [["any", "Any"], ["yes", "Has chapters"], ["breaks", "Has ad breaks"], ["no", "No chapters"]], "Chapters"),
      h("label", { class: "fld sm-only" }, h("span", { text: "Sort" }),
        h("select", { onchange: (e) => { const [s, d] = e.target.value.split(":"); f.sort = s; f.dir = Number(d); save(); renderLibraryBody(kind); } },
          sortChoices(kind).map(([v, t]) => h("option", { value: v, selected: `${f.sort}:${f.dir}` === v }, t))))));
    main.append(h("div", { id: "libBody" }));
    renderLibraryBody(kind);
  }
  function sortChoices(kind) {
    const c = [["title:1", "Title A–Z"], ["title:-1", "Title Z–A"], ["year:-1", "Newest"], ["year:1", "Oldest"]];
    if (kind === "tv") c.push(["episodes:-1", "Most episodes"], ["hours:-1", "Most hours"], ["chapters:-1", "Most chaptered"]);
    else c.push(["runtime:-1", "Longest"], ["runtime:1", "Shortest"], ["chapters:-1", "Most chapters"], ["breaks:-1", "Most ad breaks"]);
    c.push(["channels:-1", "On most channels"]);
    return c;
  }
  function renderLibraryBody(kind) {
    const body = $("#libBody");
    if (!body) return;
    const f = S.lib[kind];
    const items = filtered(kind);
    const pages = Math.max(1, Math.ceil(items.length / PAGE));
    f.page = Math.min(f.page, pages - 1);
    const slice = items.slice(f.page * PAGE, f.page * PAGE + PAGE);
    const tv = kind === "tv";
    const type = tv ? "show" : "movie";
    const sortBtn = (k, label, cls) => h("button", { type: "button", class: (f.sort === k ? "sorted " : "") + (cls || ""),
      onclick: () => { if (f.sort === k) f.dir = -f.dir; else { f.sort = k; f.dir = k === "title" ? 1 : -1; } renderLibraryBody(kind); } },
      label + (f.sort === k ? (f.dir > 0 ? " ▲" : " ▼") : ""));
    const pageAll = h("input", { type: "checkbox", "aria-label": "Select all on this page", onchange: (e) => {
      for (const x of slice) toggleSel(type, x.id, e.target.checked, false);
      S.ctxFrom = null; renderLibraryBody(kind); updateBar();
    } });
    pageAll.checked = slice.length > 0 && slice.every((x) => S.sel.has(`${type}:${x.id}`));
    const rows = h("div", { class: "rows" });
    if (tv) {
      rows.append(h("div", { class: "row head cols-tv" }, h("span", {}, pageAll), h("span", {}, sortBtn("title", "Title")),
        h("span", { class: "c" }, sortBtn("episodes", "Eps")), h("span", { class: "c" }, "Seasons"), h("span", { class: "c" }, sortBtn("hours", "Hours")),
        h("span", { class: "c" }, sortBtn("res", "Res")), h("span", {}, sortBtn("chapters", "Chapters / breaks")), h("span", {}, sortBtn("channels", "Channels"))));
    } else {
      rows.append(h("div", { class: "row head cols-mv" }, h("span", {}, pageAll), h("span", {}, sortBtn("title", "Title")),
        h("span", { class: "c" }, sortBtn("runtime", "Runtime")), h("span", { class: "c" }, sortBtn("year", "Year")),
        h("span", { class: "c" }, sortBtn("res", "Res")), h("span", {}, sortBtn("chapters", "Chapters / breaks")), h("span", {}, sortBtn("channels", "Channels"))));
    }
    for (const x of slice) {
      const key = `${type}:${x.id}`;
      const cb = h("input", { type: "checkbox", "aria-label": `Select ${x.t}`, checked: S.sel.has(key), onchange: (e) => {
        toggleSel(type, x.id, e.target.checked, false); S.ctxFrom = null; e.target.closest(".row").classList.toggle("sel", e.target.checked); updateBar();
      } });
      const chans = h("span", { class: "chans" }, x.on.length ? x.on.map(chChip) : h("span", { class: "muted small", text: "not on a channel" }));
      if (tv) {
        const sub = [x.y, x.r, (x.g || []).slice(0, 3).join(", ")].filter(Boolean).join(" · ");
        rows.append(h("div", { class: "row cols-tv" + (S.sel.has(key) ? " sel" : "") },
          h("span", { class: "cb" }, cb),
          h("span", { class: "title wide" }, x.t, h("div", { class: "sub", text: sub })),
          h("span", { class: "facts-line" },
            h("span", { class: "c" }, fmt(x.n), h("span", { class: "lbl", text: " eps" })),
            h("span", { class: "c" }, fmt(x.se), h("span", { class: "lbl", text: x.se === 1 ? " season" : " seasons" })),
            h("span", { class: "c" }, fmt(x.h, 1), h("span", { class: "lbl", text: " h" })),
            h("span", { class: "c" }, x.q),
            h("span", { class: "c small", title: `${x.ch} of ${x.n} episodes have chapters; ${x.bre} have a qualifying ad break (${x.br} breaks)` },
              `ch ${fmt(x.ch)}/${fmt(x.n)} · br ${fmt(x.bre)}`)),
          h("span", { class: "wide" }, chans)));
      } else {
        const sub = [x.r, (x.g || []).slice(0, 3).join(", "), (x.d || []).join(", ")].filter(Boolean).join(" · ");
        rows.append(h("div", { class: "row cols-mv" + (S.sel.has(key) ? " sel" : "") },
          h("span", { class: "cb" }, cb),
          h("span", { class: "title wide" }, x.t, h("div", { class: "sub", text: sub })),
          h("span", { class: "facts-line" },
            h("span", { class: "c" }, `${fmt(x.m)} min`),
            h("span", { class: "c" }, x.y || "–"),
            h("span", { class: "c", title: x.wh || "" }, x.q),
            h("span", { class: "c small", title: `${x.ch} chapters; ${x.br} qualifying ad breaks` }, `${fmt(x.ch)} ch · ${fmt(x.br)} br`)),
          h("span", { class: "wide" }, chans)));
      }
    }
    if (!slice.length) rows.append(h("div", { class: "empty", text: "Nothing matches these filters." }));
    const go = (p) => () => { f.page = p; renderLibraryBody(kind); $("#main").scrollIntoView({ block: "start" }); window.scrollTo(0, 0); };
    const pager = h("div", { class: "pager" },
      h("span", { class: "muted" }, items.length ? `${fmt(f.page * PAGE + 1)}–${fmt(Math.min(items.length, (f.page + 1) * PAGE))} of ${fmt(items.length)}` : "0 results"),
      h("span", { class: "btns" },
        h("button", { type: "button", class: "btn small", disabled: f.page === 0, onclick: go(0) }, "First"),
        h("button", { type: "button", class: "btn small", disabled: f.page === 0, onclick: go(f.page - 1) }, "Prev"),
        h("span", { class: "muted", text: ` ${f.page + 1} / ${pages} ` }),
        h("button", { type: "button", class: "btn small", disabled: f.page >= pages - 1, onclick: go(f.page + 1) }, "Next")));
    body.replaceChildren(rows, pager);
  }

  // ---------- selection + queue bar
  function toggleSel(type, id, on, rerender = true) {
    const key = `${type}:${id}`;
    if (on) {
      const x = (type === "show" ? byId.show : byId.movie).get(id);
      S.sel.set(key, { type, id, title: x ? x.t : key, on: x ? x.on : [] });
    } else S.sel.delete(key);
    if (rerender) {
      if (S.view === "channel") render(); else updateBar();
    }
  }
  function channelOptions(includePlanned, includeNone) {
    const o = [];
    if (includeNone) o.push(h("option", { value: "" }, "— none —"));
    if (S.snap) for (const c of S.snap.channels) o.push(h("option", { value: `n:${c.number}` }, `${c.number} ${c.name}${c.mirrorOf != null ? ` (mirror of ${c.mirrorOf})` : ""}`));
    if (includePlanned) for (const p of S.planned) o.push(h("option", { value: `p:${p.id}` }, `${p.number ? p.number + " " : ""}${p.name} (planned)`));
    return o;
  }
  function refOf(v) {
    if (!v) return null;
    const [t, x] = [v.slice(0, 1), v.slice(2)];
    return t === "p" ? { planned: Number(x) } : { number: x };
  }
  function updateBar() {
    const bar = $("#queuebar");
    const n = S.sel.size;
    bar.hidden = n === 0;
    document.body.classList.toggle("has-bar", n > 0);
    if (!n) return;
    $("#qbCount").textContent = `${n} selected`;
    const action = $("#qbAction").value;
    const fromSel = $("#qbFrom"), toSel = $("#qbTo");
    const keepFrom = fromSel.value, keepTo = toSel.value;
    fromSel.replaceChildren(...channelOptions(false, false));
    toSel.replaceChildren(...channelOptions(true, action === "note"));
    // default "from": the channel being viewed, else a channel every selected
    // item is on; a mirror (HD twin) stands for its source channel. Once the
    // user has picked one, theirs stays
    let from = keepFrom;
    const items = [...S.sel.values()];
    const common = items.reduce((acc, x) => acc.filter((c) => x.on.includes(c)), items[0].on.slice());
    if (!bar.dataset.fromTouched) {
      if (S.ctxFrom && S.view === "channel") from = `n:${srcNum(S.ctxFrom)}`;
      else if (common.length) from = `n:${srcNum(common[0])}`;
    }
    if (from) fromSel.value = from;
    if (keepTo) toSel.value = keepTo;
    $("#qbFromWrap").classList.toggle("hidden", !(action === "remove" || action === "move"));
    $("#qbToWrap").classList.toggle("hidden", action === "remove");
    $("#qbToLabel").textContent = action === "note" ? "About channel" : "To";
  }
  $("#qbAction").addEventListener("change", updateBar);
  $("#qbFrom").addEventListener("change", () => { $("#queuebar").dataset.fromTouched = "1"; });
  $("#qbClear").addEventListener("click", () => { S.sel.clear(); delete $("#queuebar").dataset.fromTouched; render(); });
  $("#qbShow").addEventListener("click", () => {
    const names = [...S.sel.values()].map((x) => x.title);
    toast(names.slice(0, 12).join(", ") + (names.length > 12 ? ` and ${names.length - 12} more` : ""));
  });
  $("#queuebar").addEventListener("submit", async (e) => {
    e.preventDefault();
    const action = $("#qbAction").value;
    const sent = [...S.sel.keys()], noteText = $("#qbNote").value;
    const body = { action, items: sent.map((k) => S.sel.get(k)).map(({ type, id }) => ({ type, id })), note: noteText.trim() || null };
    if (action !== "remove") body.channel = refOf($("#qbTo").value);
    if (action === "remove" || action === "move") body.from = refOf($("#qbFrom").value);
    const btn = $("#qbSubmit"); btn.disabled = true;
    try {
      const r = await api("POST", "/api/requests", body);
      toast(`Queued #${r.id}: ${action} ${plural(r.items.length, "item")}`);
      // only what was sent: anything picked while the request was on its way stays picked
      for (const k of sent) S.sel.delete(k);
      if ($("#qbNote").value === noteText) $("#qbNote").value = "";
      delete $("#queuebar").dataset.fromTouched;
      await loadQueue(); render();
    } catch (err) { toast(err.message, true); }
    finally { btn.disabled = false; }
  });

  // ---------- queue page
  function chName(c) {
    if (!c) return "";
    if (c.planned != null) return `${c.number ? c.number + " " : ""}${c.name} (planned)`;
    return `${c.number} ${c.name || ""}`.trim();
  }
  function reqTitle(r) {
    const n = r.items.length;
    const what = n ? plural(n, r.items[0].type === "movie" && r.items.every((i) => i.type === "movie") ? "film" : r.items.every((i) => i.type === "show") ? "show" : "item") : "";
    switch (r.action) {
      case "add": return `Add ${what} to ${chName(r.channel)}`;
      case "remove": return `Remove ${what} from ${chName(r.from)}`;
      case "move": return `Move ${what} from ${chName(r.from)} to ${chName(r.channel)}`;
      default: return "Note" + (r.channel ? ` about ${chName(r.channel)}` : "") + (n ? ` (${what})` : "");
    }
  }
  function reqCard(r) {
    const del = r.status === "pending" ? h("button", { type: "button", class: "btn small danger", onclick: async () => {
      if (!confirm(`Delete request #${r.id}?`)) return;
      try { await api("DELETE", `/api/requests/${r.id}`); toast(`Deleted #${r.id}`); await loadQueue(); render(); } catch (e) { toast(e.message, true); }
    } }, "Delete") : h("span", { class: `pill ${r.status}`, text: r.status });
    return h("div", { class: "req" },
      h("div", {}, h("div", { class: "what", text: `#${r.id} ${reqTitle(r)}` }),
        h("div", { class: "meta", text: `Queued ${when(r.createdAt)}` + (r.appliedAt ? ` · ${r.status} ${when(r.appliedAt)}` : "") })),
      h("div", {}, del),
      r.items.length ? h("ul", {}, r.items.slice(0, 30).map((i) => h("li", { text: i.title })), r.items.length > 30 ? h("li", { class: "muted", text: `and ${r.items.length - 30} more` }) : null) : null,
      r.note ? h("div", { class: "note", text: r.note }) : null,
      r.result ? h("div", { class: "result", text: "Result: " + r.result }) : null);
  }
  function renderQueue(main) {
    const pending = S.requests.filter((r) => r.status === "pending").slice().reverse();
    const done = S.requests.filter((r) => r.status !== "pending").slice().sort((a, b) => (b.appliedAt || "").localeCompare(a.appliedAt || ""));
    const left = h("div", {},
      h("div", { class: "card" }, h("h3", {}, "Pending ", h("span", { class: "pill pending", text: String(pending.length) })),
        pending.length ? pending.map(reqCard) : h("p", { class: "muted", text: "Nothing queued. Tick rows in Channels, TV or Movies and use the bar at the bottom." })),
      h("div", { class: "card" }, h("h3", {}, "Done ", h("span", { class: "pill", text: String(done.length) })),
        done.length ? done.map(reqCard) : h("p", { class: "muted", text: "No requests applied or rejected yet." })));

    const planForm = h("form", { class: "form", autocomplete: "off" },
      h("label", { class: "fld" }, h("span", { text: "Name" }), h("input", { id: "planName", type: "text", required: true, maxlength: "80", placeholder: "e.g. Saturday Morning" })),
      h("div", { class: "two" },
        h("label", { class: "fld" }, h("span", { text: "Number (optional)" }), h("input", { id: "planNum", type: "text", inputmode: "decimal", maxlength: "7", placeholder: "e.g. 8" })),
        h("label", { class: "fld" }, h("span", { text: "Kind (optional)" }), h("select", { id: "planKind" },
          h("option", { value: "" }, "—"), h("option", { value: "shows" }, "Shows"), h("option", { value: "movies" }, "Movies"), h("option", { value: "mixed" }, "Mixed")))),
      h("label", { class: "fld" }, h("span", { text: "Note (optional)" }), h("input", { id: "planNote", type: "text", maxlength: "4000" })),
      h("div", {}, h("button", { type: "submit", class: "btn primary" }, "Create planned channel")));
    planForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const p = await api("POST", "/api/planned", { name: $("#planName").value, number: $("#planNum").value || null, kind: $("#planKind").value || null, note: $("#planNote").value || null });
        toast(`Planned channel "${p.name}" created`); await loadQueue(); render();
      } catch (err) { toast(err.message, true); }
    });

    const noteForm = h("form", { class: "form", autocomplete: "off" },
      h("label", { class: "fld" }, h("span", { text: "Note" }), h("textarea", { id: "freeNote", required: true, maxlength: "4000", placeholder: "Anything for the next session to pick up" })),
      h("label", { class: "fld" }, h("span", { text: "About channel (optional)" }), h("select", { id: "freeCh" }, channelOptions(true, true))),
      h("div", {}, h("button", { type: "submit", class: "btn primary" }, "Queue note")));
    noteForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const r = await api("POST", "/api/requests", { action: "note", items: [], note: $("#freeNote").value, channel: refOf($("#freeCh").value) });
        toast(`Queued note #${r.id}`); await loadQueue(); render();
      } catch (err) { toast(err.message, true); }
    });

    const right = h("div", {},
      h("div", { class: "card" }, h("h3", { text: "New channel" }), h("p", { class: "small muted", text: "Creates a planned channel you can target with add or move requests." }), planForm),
      h("div", { class: "card" }, h("h3", { text: `Planned channels (${S.planned.length})` }),
        S.planned.length ? S.planned.map((p) => h("div", { class: "req" },
          h("div", {}, h("div", { class: "what", text: `${p.number ? p.number + " " : ""}${p.name}` }),
            h("div", { class: "meta", text: [p.kind, `created ${when(p.createdAt)}`, plannedTargets(p.id) ? plural(plannedTargets(p.id), "pending request") : null].filter(Boolean).join(" · ") })),
          h("div", {}, h("button", { type: "button", class: "btn small danger", onclick: () => deletePlanned(p) }, "Delete")),
          p.note ? h("div", { class: "note", text: p.note }) : null)) : h("p", { class: "muted", text: "None yet." })),
      h("div", { class: "card" }, h("h3", { text: "Free-text note" }), noteForm),
      h("p", { class: "small muted" }, "Plain-text export (for a script or an assistant applying the queue): ", h("a", { href: "/api/requests?format=text", text: "/api/requests?format=text" })));
    main.append(h("div", { class: "toolbar" }, h("h2", { text: "Queued changes" })), h("div", { class: "qgrid" }, left, right));
  }
  async function deletePlanned(p) {
    if (!confirm(`Delete planned channel "${p.name}"?`)) return;
    try { await api("DELETE", `/api/planned/${p.id}`); toast("Deleted"); await loadQueue(); render(); } catch (e) { toast(e.message, true); }
  }

  // ---------- start
  S.chMode = store.get("chMode", "tiles") === "list" ? "list" : "tiles";
  S.popRange = [1, 7, 30].includes(store.get("popRange", 7)) ? store.get("popRange", 7) : 7;
  for (const k of ["tv", "movies"]) Object.assign(S.lib[k], store.get("lib." + k, {}), { page: 0, q: "" });
  (async () => {
    try { await Promise.all([loadSnapshot(), loadQueue()]); } catch (e) { toast("Could not load: " + e.message, true); }
    route();
    loadWatch();
  })();
  setInterval(() => { if (S.view === "popular" && !document.hidden) loadWatch(); }, 60000);
})();
