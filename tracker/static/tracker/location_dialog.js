/* The add/edit location popup. Saves with fetch, so the page behind it is never reloaded. */
window.LocationDialog = (function () {
  const dlg = document.getElementById('loc-dialog');
  if (!dlg) return { open: function () {} };

  const form = document.getElementById('loc-form');
  const title = document.getElementById('loc-title');
  const nameEl = document.getElementById('loc-name');
  const noteEl = document.getElementById('loc-note');
  const latEl = document.getElementById('loc-lat');
  const lngEl = document.getElementById('loc-lng');
  const qEl = document.getElementById('loc-q');
  const googleLinkEl = document.getElementById('loc-google-link');
  const findBtn = document.getElementById('loc-find');
  const importBtn = document.getElementById('loc-import');
  const meBtn = document.getElementById('loc-me');
  const unpinBtn = document.getElementById('loc-unpin');
  const cancelBtn = document.getElementById('loc-cancel');
  const results = document.getElementById('loc-results');
  const errEl = document.getElementById('loc-error');
  const mapEl = document.getElementById('loc-map');
  const mapTools = document.getElementById('loc-maptools');
  const noMap = document.getElementById('loc-nomap');
  const saveBtn = form.querySelector('button[type="submit"]');

  let map = null;
  let marker = null;
  let current = {};

  function showError(msg) {
    errEl.textContent = msg;
    errEl.hidden = !msg;
  }

  function setPin(lat, lng, zoomIn) {
    latEl.value = lat.toFixed(6);
    lngEl.value = lng.toFixed(6);
    if (!map) return;
    if (!marker) {
      marker = L.marker([lat, lng], { icon: MapKit.pin(0, 'draft'), draggable: true }).addTo(map);
      marker.on('dragend', function () {
        const p = marker.getLatLng();
        latEl.value = p.lat.toFixed(6);
        lngEl.value = p.lng.toFixed(6);
      });
    } else {
      marker.setLatLng([lat, lng]);
    }
    if (zoomIn) map.setView([lat, lng], Math.max(map.getZoom(), 15));
  }

  function clearPin() {
    latEl.value = '';
    lngEl.value = '';
    if (marker && map) map.removeLayer(marker);
    marker = null;
  }

  function coordinatesFrom(value) {
    const text = value.trim();
    if (!text) return null;

    function pair(value) {
      const match = String(value).match(/^\s*(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$/);
      if (!match) return null;
      const lat = Number(match[1]), lng = Number(match[2]);
      return Number.isFinite(lat) && Number.isFinite(lng) &&
        lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180 ? [lat, lng] : null;
    }

    const direct = pair(text);
    if (direct) return direct;

    // Coordinates occur in full Google Maps links as @lat,lng, !3dlat!4dlng,
    // or in q/ll/query parameters. A short maps.app.goo.gl link cannot be
    // resolved client-side without a Google API, so we explain that below.
    const decoded = text.replace(/&amp;/g, '&');
    const patterns = [
      /@(-?\d{1,3}(?:\.\d+)?),\s*(-?\d{1,3}(?:\.\d+)?)/i,
      /!3d(-?\d{1,3}(?:\.\d+)?)!4d(-?\d{1,3}(?:\.\d+)?)/i,
    ];
    for (const pattern of patterns) {
      const match = decoded.match(pattern);
      if (match) {
        const result = pair(match[1] + ',' + match[2]);
        if (result) return result;
      }
    }
    try {
      const url = new URL(text);
      for (const key of ['q', 'query', 'll', 'center', 'destination']) {
        const result = pair(url.searchParams.get(key) || '');
        if (result) return result;
      }
    } catch (err) {
      // Not a URL; the coordinate-pair check above already handled plain text.
    }
    return null;
  }

  function open(opts) {
    current = opts || {};
    const loc = current.location || null;
    form.reset();
    showError('');
    results.hidden = true;
    results.textContent = '';
    title.textContent = loc ? 'Edit location' : 'Add location';
    nameEl.value = loc ? loc.name : current.name || '';
    noteEl.value = loc ? loc.note || '' : '';
    dlg.showModal();

    const hasMap = MapKit.ok();
    mapEl.hidden = !hasMap;
    mapTools.hidden = !hasMap;
    noMap.hidden = hasMap;
    if (!hasMap) return;

    if (!map) {
      map = MapKit.createMap(mapEl);
      map.on('click', function (e) {
        setPin(e.latlng.lat, e.latlng.lng, false);
      });
    }
    clearPin();
    // The map was hidden until now, so it must re-measure itself.
    setTimeout(function () {
      map.invalidateSize();
      let lat = current.lat;
      let lng = current.lng;
      if (loc && loc.lat !== null && loc.lng !== null) {
        lat = loc.lat;
        lng = loc.lng;
      }
      if (typeof lat === 'number' && typeof lng === 'number') {
        setPin(lat, lng, true);
      } else {
        map.setView(MapKit.cfg.center, MapKit.cfg.zoom);
      }
    }, 60);
  }

  async function find() {
    const q = qEl.value.trim();
    if (!q) return;
    results.hidden = false;
    results.textContent = '';
    const wait = document.createElement('li');
    wait.textContent = 'Searching...';
    results.appendChild(wait);
    try {
      const res = await fetch(
        'https://nominatim.openstreetmap.org/search?format=jsonv2&limit=5&q=' + encodeURIComponent(q),
        { headers: { Accept: 'application/json' } }
      );
      const items = await res.json();
      results.textContent = '';
      if (!items.length) {
        const none = document.createElement('li');
        none.textContent = 'Nothing found. Try a nearby town or click the map instead.';
        results.appendChild(none);
        return;
      }
      items.forEach(function (it) {
        const li = document.createElement('li');
        li.tabIndex = 0;
        li.textContent = it.display_name;
        const choose = function () {
          setPin(parseFloat(it.lat), parseFloat(it.lon), true);
          if (!noteEl.value) noteEl.value = it.display_name.slice(0, 300);
          if (!nameEl.value) nameEl.value = (it.name || it.display_name.split(',')[0]).slice(0, 200);
          results.hidden = true;
        };
        li.addEventListener('click', choose);
        li.addEventListener('keydown', function (e) {
          if (e.key === 'Enter') {
            e.preventDefault();
            choose();
          }
        });
        results.appendChild(li);
      });
    } catch (err) {
      results.textContent = '';
      const bad = document.createElement('li');
      bad.textContent = 'Search failed. Check your internet connection, or click the map instead.';
      results.appendChild(bad);
    }
  }

  findBtn.addEventListener('click', find);
  importBtn.addEventListener('click', function () {
    const coords = coordinatesFrom(googleLinkEl.value);
    if (!coords) {
      showError('No coordinates found. Paste a full Google Maps link or enter latitude, longitude. Short maps.app.goo.gl links need to be opened and copied as a full link first.');
      return;
    }
    showError('');
    setPin(coords[0], coords[1], true);
  });
  googleLinkEl.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      importBtn.click();
    }
  });
  qEl.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      find();
    }
  });

  meBtn.addEventListener('click', function () {
    if (!navigator.geolocation) {
      showError('Your browser cannot share your location.');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        showError('');
        setPin(pos.coords.latitude, pos.coords.longitude, true);
      },
      function () {
        showError('Could not get your location. Allow location access, or click the map instead.');
      }
    );
  });

  unpinBtn.addEventListener('click', clearPin);
  cancelBtn.addEventListener('click', function () {
    dlg.close();
  });

  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    showError('');
    const loc = current.location || null;
    const url = loc ? dlg.dataset.updateUrl.replace('/0/', '/' + loc.id + '/') : dlg.dataset.createUrl;
    saveBtn.disabled = true;
    try {
      const res = await fetch(url, {
        method: 'POST',
        body: new FormData(form),
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      let data = null;
      try {
        data = await res.json();
      } catch (err) {
        data = null;
      }
      if (res.ok && data && data.ok) {
        dlg.close();
        if (current.onSaved) current.onSaved(data.location, !!loc);
      } else {
        showError((data && data.error) || 'Could not save this location. Try again.');
      }
    } catch (err) {
      showError('Could not reach the server. Try again.');
    } finally {
      saveBtn.disabled = false;
    }
  });

  return { open: open };
})();
