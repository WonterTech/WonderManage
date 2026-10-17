/* The Locations page: list on the left, every saved pin on the map. */
(function () {
  const mapEl = document.getElementById('places-map');
  if (!mapEl) return;

  const data = JSON.parse(document.getElementById('places-data').textContent);
  const urls = JSON.parse(document.getElementById('places-urls').textContent);
  const byId = {};
  data.forEach(function (p) {
    byId[p.id] = p;
  });
  const reload = function () {
    window.location.reload();
  };
  const items = Array.prototype.slice.call(document.querySelectorAll('#place-items li.place'));

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function fmtDue(iso) {
    if (!iso) return '';
    return new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
  }

  function plural(n, word) {
    return n + ' ' + word + (n === 1 ? '' : 's');
  }

  /* ---------- the popup shown on the map ---------- */
  function popupFor(p) {
    const box = el('div', 'pop');
    box.appendChild(el('strong', '', p.name));
    if (p.note) box.appendChild(el('div', 'pop-note', p.note));

    const chips = el('div', 'pchips');
    chips.appendChild(el('span', 'pchip' + (p.open ? ' open' : ''), p.open ? plural(p.open, 'open task') : 'No open tasks'));
    if (p.done) chips.appendChild(el('span', 'pchip', p.done + ' done'));
    box.appendChild(chips);

    if (p.tasks && p.tasks.length) {
      box.appendChild(el('h4', '', 'Next tasks'));
      const ul = el('ul');
      p.tasks.forEach(function (t) {
        const li = el('li');
        li.appendChild(el('div', '', t.title));
        if (t.due) li.appendChild(el('span', '', fmtDue(t.due)));
        ul.appendChild(li);
      });
      box.appendChild(ul);
    }
    if (p.clients && p.clients.length) {
      box.appendChild(el('h4', '', 'Clients'));
      box.appendChild(el('div', 'pop-note', p.clients.join(', ')));
    }
    if (p.suppliers && p.suppliers.length) {
      box.appendChild(el('h4', '', 'Suppliers'));
      box.appendChild(el('div', 'pop-note', p.suppliers.join(', ')));
    }

    const links = el('div', 'pop-links');
    if (p.lat !== null && p.lng !== null) {
      const dir = el('a', 'mini main', 'Directions');
      dir.href = 'https://www.google.com/maps/dir/?api=1&destination=' + encodeURIComponent(p.lat + ',' + p.lng);
      dir.target = '_blank';
      dir.rel = 'noopener';
      links.appendChild(dir);
    }
    if (urls.canAddTask) {
      const add = el('a', 'mini', 'Add task here');
      add.href = urls.newTask + '?place=' + p.id + '&next=' + encodeURIComponent(window.location.pathname);
      links.appendChild(add);
    }
    if (urls.canViewTasks) {
      const all = el('a', 'mini', 'All tasks');
      all.href = urls.tasks + '?place=' + p.id + '&status=all';
      links.appendChild(all);
    }
    if (urls.canEdit) {
      const edit = el('button', 'mini', 'Edit');
      edit.type = 'button';
      edit.addEventListener('click', function () {
        if (map) map.closePopup();
        editPlace(p.id);
      });
      links.appendChild(edit);
    }
    if (links.children.length) box.appendChild(links);
    return box;
  }

  function editPlace(id) {
    if (!urls.canEdit) return;
    LocationDialog.open({ location: byId[id], onSaved: reload });
  }

  /* ---------- highlight the selected place in the list ---------- */
  function setActive(id, scroll) {
    items.forEach(function (li) {
      li.classList.toggle('active', Number(li.dataset.id) === id);
    });
    if (scroll && id !== null) {
      const li = document.getElementById('place-' + id);
      if (li && !li.hidden) li.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }

  /* ---------- add / edit buttons ---------- */
  const addBtn = document.getElementById('add-place');
  if (addBtn) {
    addBtn.addEventListener('click', function () {
      LocationDialog.open({ onSaved: reload });
    });
  }
  document.querySelectorAll('.js-edit').forEach(function (b) {
    b.addEventListener('click', function () {
      const menu = b.closest('details');
      if (menu) menu.open = false;
      editPlace(Number(b.dataset.id));
    });
  });

  /* ---------- copy map link ---------- */
  document.addEventListener('click', async function (e) {
    const button = e.target.closest('.js-copy-map');
    if (!button) return;
    const original = button.textContent;
    try {
      await navigator.clipboard.writeText(button.dataset.url);
      button.textContent = 'Link copied';
    } catch (err) {
      window.prompt('Copy this Google Maps link:', button.dataset.url);
    }
    window.setTimeout(function () { button.textContent = original; }, 1800);
  });

  /* ---------- the "..." menus: only one open, close on outside click or Escape ---------- */
  const menus = Array.prototype.slice.call(document.querySelectorAll('details.pmore'));
  menus.forEach(function (d) {
    d.addEventListener('toggle', function () {
      if (d.open) menus.forEach(function (o) { if (o !== d) o.open = false; });
    });
  });
  document.addEventListener('click', function (e) {
    menus.forEach(function (d) { if (d.open && !d.contains(e.target)) d.open = false; });
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') menus.forEach(function (d) { d.open = false; });
  });

  /* ---------- search + quick filters + counter ---------- */
  const filter = document.getElementById('places-filter');
  const chips = Array.prototype.slice.call(document.querySelectorAll('.fchip'));
  const counter = document.getElementById('loc-count');
  const noMatch = document.getElementById('no-match');
  let mode = 'all';

  function applyFilter() {
    const q = filter.value.trim().toLowerCase();
    let shown = 0;
    items.forEach(function (li) {
      const okText = q === '' || li.dataset.search.indexOf(q) !== -1;
      const okMode = mode === 'all' ||
        (mode === 'busy' && Number(li.dataset.open) > 0) ||
        (mode === 'nopin' && li.dataset.pin === '0');
      li.hidden = !(okText && okMode);
      if (!li.hidden) shown += 1;
    });
    if (noMatch) noMatch.hidden = items.length === 0 || shown > 0;
    if (counter) {
      counter.textContent = items.length === 0 ? '' :
        (shown === items.length ? plural(items.length, 'location') : shown + ' of ' + plural(items.length, 'location'));
    }
  }
  filter.addEventListener('input', applyFilter);
  chips.forEach(function (c) {
    c.addEventListener('click', function () {
      mode = c.dataset.mode;
      chips.forEach(function (o) { o.setAttribute('aria-pressed', o === c ? 'true' : 'false'); });
      applyFilter();
    });
  });
  applyFilter();

  /* ---------- the map ---------- */
  let map = null;
  if (!MapKit.ok()) {
    mapEl.classList.add('nomap');
    mapEl.textContent = "The map couldn't load. Check your internet connection and refresh.";
    document.querySelectorAll('.js-show').forEach(function (b) {
      b.addEventListener('click', function () {
        editPlace(Number(b.dataset.id));
      });
    });
    return;
  }

  map = MapKit.createMap(mapEl);
  const markers = {};
  const bounds = [];
  data.forEach(function (p) {
    if (p.lat === null || p.lng === null) return;
    const m = L.marker([p.lat, p.lng], {
      icon: MapKit.pin(p.open, p.open > 0 ? 'busy' : 'idle'),
      title: p.name,
      keyboard: true,
    }).addTo(map);
    m.bindPopup(function () {
      return popupFor(p);
    }, { maxWidth: 320 });
    m.on('popupopen', function () { setActive(p.id, true); });
    m.on('popupclose', function () { setActive(null, false); });
    markers[p.id] = m;
    bounds.push([p.lat, p.lng]);
  });
  if (bounds.length) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });

  if (urls.canAdd) map.on('click', function (e) {
    const box = el('div', 'pop');
    const b = el('button', 'btn', 'Add a location here');
    b.type = 'button';
    b.addEventListener('click', function () {
      map.closePopup();
      LocationDialog.open({ lat: e.latlng.lat, lng: e.latlng.lng, onSaved: reload });
    });
    box.appendChild(b);
    L.popup().setLatLng(e.latlng).setContent(box).openOn(map);
  });

  document.querySelectorAll('.js-show').forEach(function (b) {
    b.addEventListener('click', function () {
      const id = Number(b.dataset.id);
      const m = markers[id];
      if (!m) {
        editPlace(id);
        return;
      }
      // On a phone the map sits above the list: bring it into view first.
      if (window.matchMedia('(max-width: 860px)').matches) {
        mapEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
      map.flyTo(m.getLatLng(), Math.max(map.getZoom(), 14));
      m.openPopup();
    });
  });
})();
