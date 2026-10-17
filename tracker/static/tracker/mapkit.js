/* Shared map helpers. Needs Leaflet (window.L) and a #map-config JSON script on the page. */
window.MapKit = (function () {
  const cfg = JSON.parse(document.getElementById('map-config').textContent);

  function ok() {
    return typeof window.L !== 'undefined';
  }

  function createMap(el) {
    const map = L.map(el).setView(cfg.center, cfg.zoom);
    L.tileLayer(cfg.tileUrl, {
      maxZoom: 19,
      attribution: cfg.attribution,
      // Tile servers want to know which site is asking; send the origin even though Django's default policy hides it.
      referrerPolicy: 'strict-origin-when-cross-origin',
    }).addTo(map);
    return map;
  }

  // kind: 'busy' (has open tasks), 'idle' (no open tasks) or 'draft' (the pin being placed)
  function pin(count, kind) {
    const n = Number(count) > 0 ? '<b>' + Number(count) + '</b>' : '';
    return L.divIcon({
      className: '',
      html: '<div class="pin ' + kind + '"><i></i>' + n + '</div>',
      iconSize: [28, 34],
      iconAnchor: [14, 34],
      popupAnchor: [0, -32],
    });
  }

  return { cfg: cfg, ok: ok, createMap: createMap, pin: pin };
})();
