// Country selection, map navigation and hover details.
export default function ({ parentElement, data, setTriggerValue }) {
  const plot = parentElement.querySelector(".q5-map-plot");
  const error = parentElement.querySelector(".q5-map-error");
  const tools = parentElement.querySelector(".q5-map-tools");
  const region = tools.querySelector("select");
  const controls = [...tools.querySelectorAll("button,select")];
  const viewKey = data.figure.layout.uirevision;
  window.__spotifyQ5Views ||= {};
  // Reuse the camera across country and feature changes.
  const previous = window.__spotifyQ5Views[viewKey];
  const saved = previous?.schema === 2 && previous.projectionType === "natural earth"
    && [...region.options].some(option => option.value === previous.region)
    ? previous : null;
  region.value = saved?.region || "world";
  controls.forEach(control => { control.disabled = true; });
  plot.style.height = data.figure.layout.height + "px";
  plot.style.position = "relative";
  let cancelled = false;
  let busy = false;
  let pointer = null;
  let positionFrame = 0;
  const tooltip = document.createElement("div");
  tooltip.className = "q5-cursor-tooltip";
  tooltip.setAttribute("role", "tooltip");
  tooltip.hidden = true;
  Object.assign(tooltip.style, {
    position: "fixed", pointerEvents: "none", zIndex: "10000",
    boxSizing: "border-box", maxWidth: "280px", padding: "10px 12px",
    border: "1px solid #CAD5E0", borderRadius: "7px", background: "white",
    color: "#17324D", boxShadow: "0 4px 16px rgba(23,50,77,.16)",
    font: "13px/1.45 Arial,sans-serif", overflowWrap: "anywhere"
  });
  document.body.appendChild(tooltip);

  function placeTooltip() {
    positionFrame = 0;
    if (cancelled || tooltip.hidden || !pointer || !plot.isConnected) return;
    const area = plot.getBoundingClientRect();
    const pad = 8, gap = 14;
    const left = Math.max(pad, area.left + pad);
    const right = Math.min(window.innerWidth - pad, area.right - pad);
    const top = Math.max(pad, area.top + pad);
    const bottom = Math.min(window.innerHeight - pad, area.bottom - pad);
    tooltip.style.maxWidth = Math.max(120, Math.min(280, right - left)) + "px";
    const size = tooltip.getBoundingClientRect();
    let x = pointer.x + gap;
    let y = pointer.y + gap;
    if (x + size.width > right) x = pointer.x - size.width - gap;
    if (y + size.height > bottom) y = pointer.y - size.height - gap;
    tooltip.style.left = Math.max(left, Math.min(x, right - size.width)) + "px";
    tooltip.style.top = Math.max(top, Math.min(y, bottom - size.height)) + "px";
  }
  function followPointer(event) {
    pointer = { x: event.clientX, y: event.clientY, buttons: event.buttons };
    if (event.buttons) { hideHover(); return; }
    if (!tooltip.hidden && !positionFrame) positionFrame = requestAnimationFrame(placeTooltip);
  }
  function showTooltip(details) {
    if (!details || details.length < 11 || !pointer || pointer.buttons) return;
    // All content is inserted as text; no CSV metadata is interpreted as HTML.
    tooltip.replaceChildren();
    const title = document.createElement("div");
    title.textContent = details[1];
    Object.assign(title.style, { fontWeight: "700", fontSize: "14px", marginBottom: "4px" });
    tooltip.appendChild(title);
    const lines = [`Date: ${details[2]}`, `Feature: ${details[3]}`];
    if (details[9] === "Available") {
      lines.push(`Median: ${details[4]}`, `Q1 / Q3: ${details[5]} / ${details[6]}`);
    } else {
      lines.push("Insufficient data", `At least ${details[10]}/50 valid tracks required`);
    }
    lines.push(`Valid tracks: ${details[7]}/${details[8]}`);
    for (const text of lines) {
      const line = document.createElement("div");
      line.textContent = text;
      tooltip.appendChild(line);
    }
    tooltip.dataset.country = details[0];
    tooltip.dataset.feature = data.feature;
    tooltip.hidden = false;
    placeTooltip();
  }
  const hint = document.createElement("span");
  hint.className = "q5-hover-pin";
  hint.setAttribute("aria-hidden", "true");
  hint.hidden = true;
  Object.assign(hint.style, {
    position: "absolute", width: "8px", height: "8px", borderRadius: "50%",
    border: "1.5px solid white", boxShadow: "0 0 0 1px rgba(23,50,77,.22)",
    transform: "translate(-50%,-50%)", pointerEvents: "none", zIndex: "2"
  });
  plot.appendChild(hint);
  const hideHint = () => { hint.hidden = true; delete hint.dataset.country; };
  function hideHover() {
    hideHint();
    tooltip.hidden = true;
    delete tooltip.dataset.country;
  }
  plot.addEventListener("pointermove", followPointer);
  plot.addEventListener("pointerleave", hideHover);
  plot.addEventListener("pointerdown", hideHover);

  function saveView() {
    const geo = plot._fullLayout?.geo;
    if (!geo) return;
    window.__spotifyQ5Views[viewKey] = {
      schema: 2,
      scale: geo.projection.scale, center: { ...geo.center },
      rotation: { ...geo.projection.rotation }, region: region.value,
      projectionType: geo.projection.type,
      latitudeRange: [...geo.lataxis.range], longitudeRange: [...geo.lonaxis.range]
    };
  }
  const resize = new ResizeObserver(() => {
    if (!cancelled && window.Plotly && plot.isConnected && plot.offsetWidth > 0 && plot.offsetHeight > 0 && plot.dataset.ready === "true") {
      // A view change can detach the plot before its deferred resize finishes.
      const pending = window.Plotly.Plots.resize(plot);
      if (pending?.catch) pending.catch(() => {});
    }
  });
  resize.observe(plot);

  error.hidden = true;
  plot.style.display = "block";
  plot.dataset.ready = "false";
  plot.setAttribute("aria-label", `${data.feature_label}: median audio characteristic by country`);
  Promise.resolve(window.Plotly).then(async (Plotly) => {
    if (!Plotly) throw new Error("Bundled Plotly is unavailable");
    const topology = window.PlotlyGeoAssets?.topojson?.world_50m;
    if (topology.type !== "Topology" || !topology.objects?.countries) throw new Error("Invalid local world geometry");
    if (cancelled) return;
    const layout = { ...data.figure.layout, geo: { ...data.figure.layout.geo } };
    if (saved) {
      layout.geo.center = saved.center;
      layout.geo.projection = { ...layout.geo.projection, type: saved.projectionType,
        scale: saved.scale, rotation: saved.rotation };
      layout.geo.lataxis = { ...layout.geo.lataxis, range: saved.latitudeRange };
      layout.geo.lonaxis = { ...layout.geo.lonaxis, range: saved.longitudeRange };
    }
    await Plotly.react(plot, data.figure.data, layout, {
      displaylogo: false, responsive: true,
      scrollZoom: true, displayModeBar: false
    });
    if (cancelled) return;

    // Give tiny countries a 16-pixel click target.
    const seen = new Set();
    const tiny = [...plot.querySelectorAll("path.choroplethlocation")].flatMap(path => {
      const point = path.__data__;
      const box = path.getBoundingClientRect();
      const code = point?.data?.[0];
      if (!data.valid_codes.includes(code) || seen.has(code) || !Array.isArray(point?.ct)) return [];
      if (!(box.width > 0 && box.height > 0 && box.width <= 5 && box.height <= 5)) return [];
      seen.add(code);
      return [{ code, center: point.ct, hover: point.tx, details: point.data }];
    });
    if (tiny.length) {
      await Plotly.addTraces(plot, {
        type: "scattergeo", mode: "markers", name: "Small-country click targets",
        lon: tiny.map(p => p.center[0]), lat: tiny.map(p => p.center[1]),
        customdata: tiny.map(p => p.details), text: tiny.map(p => p.hover),
        marker: { symbol: "circle", size: 16, opacity: 0,
          color: tiny.map(p => p.code === data.country_a ? "#0072B2" : p.code === data.country_b ? "#D55E00" : "#475569"),
          line: { width: 1.8 } },
        hovertemplate: "%{text}<br><i>Click to select this country</i><extra></extra>",
        showlegend: false, meta: { kind: "small_country_click_targets" }
      });
    }
    if (cancelled) return;
    plot.removeAllListeners("plotly_click");
    plot.on("plotly_click", (event) => {
      const point = event.points?.find(p => p.customdata?.[0]);
      const code = point?.customdata?.[0];
      if (!data.valid_codes.includes(code)) return;
      setTriggerValue("country_click", { code, target: data.target, event_id: Date.now() });
    });
    plot.removeAllListeners("plotly_hover");
    plot.removeAllListeners("plotly_unhover");
    plot.on("plotly_hover", event => {
      const hovered = event.points?.find(p => data.valid_codes.includes(p.customdata?.[0]));
      if (hovered) showTooltip(hovered.customdata);
      else { hideHover(); return; }
      const point = event.points?.find(p => p.data?.meta?.kind === "small_country_click_targets");
      const target = point && tiny.find(p => p.code === point.customdata?.[0]);
      if (!target) { hideHint(); return; }
      const position = plot._fullLayout.geo._subplot.projection(target.center);
      hint.style.left = position[0] + "px";
      hint.style.top = position[1] + "px";
      hint.style.background = target.code === data.country_a ? "#0072B2" : target.code === data.country_b ? "#D55E00" : "#475569";
      hint.dataset.country = target.code;
      hint.hidden = false;
    });
    plot.on("plotly_unhover", hideHover);
    plot.removeAllListeners("plotly_relayout");
    plot.on("plotly_relayout", () => { hideHover(); saveView(); });

    async function navigate(patch) {
      if (cancelled || busy) return;
      busy = true;
      try {
        await Plotly.relayout(plot, patch);
        if (!cancelled) saveView();
      } finally {
        busy = false;
      }
    }
    const presets = {
      world: { scale: 1, lon: 0, lat: 0 },
      asia: { scale: 1.6, lon: 95, lat: 34, rotationLon: 95 },
      europe: { scale: 3.2, lon: 15, lat: 53 },
      africa: { scale: 1.8, lon: 20, lat: 1 },
      north_america: { scale: 1.8, lon: -105, lat: 40, rotationLon: -105 },
      south_america: { scale: 2, lon: -60, lat: -20 },
      oceania: { scale: 1.6, lon: 150, lat: -15, rotationLon: 150 }
    };
    function focus(name) {
      if (!presets[name]) name = "world";
      region.value = name;
      const preset = presets[name];
      // Camera presets reuse the bundled world geometry.
      return navigate({ "geo.projection.type": preset.type || "natural earth",
        "geo.projection.scale": preset.scale, "geo.center.lon": preset.lon,
        "geo.center.lat": preset.lat, "geo.projection.rotation.lon": preset.rotationLon || 0,
        "geo.projection.rotation.lat": preset.rotationLat || 0, "geo.projection.rotation.roll": 0,
        "geo.lataxis.range": preset.latitudeRange || [-58, 85], "geo.lonaxis.range": [-180, 180] });
    }
    tools.querySelector('[data-map-action="in"]').onclick = () => navigate({ "geo.projection.scale": Math.min(24, plot._fullLayout.geo.projection.scale * 1.6) });
    tools.querySelector('[data-map-action="out"]').onclick = () => navigate({ "geo.projection.scale": Math.max(1, plot._fullLayout.geo.projection.scale / 1.6) });
    tools.querySelector('[data-map-action="world"]').onclick = () => focus("world");
    region.onchange = () => focus(region.value);
    controls.forEach(control => { control.disabled = false; });
    plot.dataset.ready = "true";
    plot.dataset.feature = data.feature;
    plot.dataset.target = data.target;
    plot.dataset.countryA = data.country_a || "";
    plot.dataset.countryB = data.country_b || "";
    plot.dataset.clickTargets = JSON.stringify(tiny.map(p => p.code));
  }).catch((problem) => {
    if (cancelled) return;
    plot.style.display = "none";
    plot.dataset.ready = "false";
    error.textContent = "World map unavailable. " + problem.message + ". Check the local map resources; country search and distributions remain available.";
    error.hidden = false;
  });

  return () => {
    cancelled = true;
    resize.disconnect();
    saveView();
    plot.removeEventListener("pointermove", followPointer);
    plot.removeEventListener("pointerleave", hideHover);
    plot.removeEventListener("pointerdown", hideHover);
    if (positionFrame) cancelAnimationFrame(positionFrame);
    hint.remove();
    tooltip.remove();
    controls.forEach(control => { control.onclick = null; });
    region.onchange = null;
    if (plot.removeAllListeners) {
      plot.removeAllListeners("plotly_click");
      plot.removeAllListeners("plotly_hover");
      plot.removeAllListeners("plotly_unhover");
      plot.removeAllListeners("plotly_relayout");
    }
    if (window.Plotly && plot._fullLayout) window.Plotly.purge(plot);
  };
}
