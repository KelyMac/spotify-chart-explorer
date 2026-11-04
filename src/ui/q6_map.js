// Chart ranks for the selected song.
export default function ({parentElement, data}) {
  const plot = parentElement.querySelector('.q6-map-plot');
  const error = parentElement.querySelector('.q6-map-error');
  let cancelled = false;
  plot.style.height = data.figure.layout.height + 'px';
  const resize = new ResizeObserver(() => {
    if (window.Plotly && plot._fullLayout) window.Plotly.Plots.resize(plot);
  });
  resize.observe(plot);
  Promise.resolve().then(async () => {
    if (!window.Plotly) throw new Error('Bundled Plotly is unavailable');
    const topology = window.PlotlyGeoAssets?.topojson?.world_50m;
    if (!topology.objects?.countries) throw new Error('Invalid local geography');
    if (cancelled) return;
    await window.Plotly.newPlot(plot, data.figure.data, data.figure.layout, {
      responsive: true, displayModeBar: false, scrollZoom: true
    });
    if (cancelled) return;
    plot.dataset.ready = 'true';
    plot.dataset.song = data.figure.layout.meta.spotify_id;
  }).catch(problem => {
    if (cancelled) return;
    plot.hidden = true;
    error.hidden = false;
    error.textContent = 'World map unavailable. ' + problem.message + '. The country/rank table remains available below.';
  });
  return () => {
    cancelled = true;
    resize.disconnect();
    if (window.Plotly && plot._fullLayout) window.Plotly.purge(plot);
  };
}
