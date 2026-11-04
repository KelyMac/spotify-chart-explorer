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
  function loadPlotly() {
    if (window.Plotly) return Promise.resolve();
    window.__spotifyQ6Plotly ||= new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = data.plotly_url;
      script.onload = resolve;
      script.onerror = () => { window.__spotifyQ6Plotly = null; reject(new Error('Local Plotly could not load')); };
      document.head.appendChild(script);
    });
    return window.__spotifyQ6Plotly;
  }
  Promise.all([loadPlotly(), fetch(data.topojson_url + 'world_50m.json').then(async response => {
    if (!response.ok) throw new Error('Local geography HTTP ' + response.status);
    const topology = await response.json();
    if (!topology.objects?.countries) throw new Error('Invalid local geography');
  })]).then(async () => {
    if (cancelled) return;
    await window.Plotly.newPlot(plot, data.figure.data, data.figure.layout, {
      responsive: true, displayModeBar: false, scrollZoom: true, topojsonURL: data.topojson_url
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
