/* Search-and-pick box for a task's location, with inline "add new". */
(function () {
  const dataEl = document.getElementById('locations-data');
  const input = document.getElementById('place-search');
  if (!dataEl || !input) return;

  const data = JSON.parse(dataEl.textContent);
  const hidden = document.getElementById('id_place');
  const list = document.getElementById('place-list');
  const clearBtn = document.getElementById('place-clear');
  const taskForm = document.getElementById('task-form');
  const canAdd = input.dataset.canAdd === '1';
  let shown = [];
  let active = -1;

  const norm = function (s) {
    return s.trim().toLowerCase();
  };
  const isOpen = function () {
    return !list.hidden;
  };

  function close() {
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    active = -1;
  }

  function setActive(i) {
    active = i;
    Array.prototype.forEach.call(list.children, function (li, idx) {
      li.setAttribute('aria-selected', idx === i ? 'true' : 'false');
    });
    if (i >= 0) {
      input.setAttribute('aria-activedescendant', list.children[i].id);
      list.children[i].scrollIntoView({ block: 'nearest' });
    } else {
      input.removeAttribute('aria-activedescendant');
    }
  }

  function select(loc) {
    hidden.value = loc ? String(loc.id) : '';
    input.value = loc ? loc.name : '';
    clearBtn.hidden = !loc;
    close();
  }

  function openAdd(name) {
    close();
    LocationDialog.open({
      name: name,
      onSaved: function (loc) {
        data.push(loc);
        select(loc);
        input.focus();
      },
    });
  }

  function choose(item) {
    if (item.kind === 'add') openAdd(item.name);
    else select(item.loc);
  }

  function defaultIndex() {
    const q = norm(input.value);
    const exact = shown.findIndex(function (it) {
      return it.kind === 'loc' && norm(it.loc.name) === q;
    });
    if (exact >= 0) return exact;
    const add = shown.findIndex(function (it) {
      return it.kind === 'add';
    });
    return add;
  }

  function render() {
    const q = norm(input.value);
    const matches = data
      .filter(function (l) {
        return !q || l.name.toLowerCase().indexOf(q) !== -1 || (l.note || '').toLowerCase().indexOf(q) !== -1;
      })
      .sort(function (a, b) {
        return a.name.localeCompare(b.name);
      })
      .slice(0, 8);
    shown = matches.map(function (loc) {
      return { kind: 'loc', loc: loc };
    });
    const exactExists = data.some(function (l) {
      return norm(l.name) === q;
    });
    if (q && !exactExists && canAdd) shown.push({ kind: 'add', name: input.value.trim() });

    list.textContent = '';
    shown.forEach(function (item, i) {
      const li = document.createElement('li');
      li.id = 'place-opt-' + i;
      li.setAttribute('role', 'option');
      li.setAttribute('aria-selected', 'false');
      if (item.kind === 'add') {
        li.className = 'add';
        li.textContent = 'Add "' + item.name + '" as a new location';
      } else {
        li.textContent = item.loc.name;
        const detail = [];
        if (item.loc.note) detail.push(item.loc.note);
        detail.push(item.loc.lat === null ? 'no map pin yet' : 'on the map');
        const small = document.createElement('small');
        small.textContent = detail.join(' - ');
        li.appendChild(small);
      }
      // mousedown, so the choice lands before the input loses focus
      li.addEventListener('mousedown', function (e) {
        e.preventDefault();
        choose(item);
      });
      list.appendChild(li);
    });
    list.hidden = shown.length === 0;
    input.setAttribute('aria-expanded', String(!list.hidden));
    active = -1;
  }

  input.addEventListener('focus', render);
  input.addEventListener('input', function () {
    // Editing the text un-picks the current place until a new one is chosen.
    hidden.value = '';
    input.setCustomValidity('');
    clearBtn.hidden = true;
    render();
  });

  input.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!isOpen()) render();
      if (shown.length) setActive(active + 1 >= shown.length ? 0 : active + 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (shown.length) setActive(active <= 0 ? shown.length - 1 : active - 1);
    } else if (e.key === 'Enter') {
      if (isOpen() && shown.length) {
        const idx = active >= 0 ? active : defaultIndex();
        if (idx >= 0) {
          e.preventDefault();
          choose(shown[idx]);
        }
      }
    } else if (e.key === 'Escape') {
      if (isOpen()) {
        e.preventDefault();
        close();
      }
    }
  });

  document.addEventListener('mousedown', function (e) {
    if (!e.target.closest('.combo')) close();
  });

  clearBtn.addEventListener('click', function () {
    select(null);
    input.focus();
  });

  // Saving the task with text that was never picked: match it, or offer to add it. Never drop it silently.
  taskForm.addEventListener('submit', function (e) {
    const text = input.value.trim();
    if (text && !hidden.value) {
      const match = data.find(function (l) {
        return norm(l.name) === norm(text);
      });
      if (match) {
        select(match);
        return;
      }
      e.preventDefault();
      if (canAdd) {
        openAdd(text);
      } else {
        input.setCustomValidity("Pick one of your saved places. You don't have permission to add new ones.");
        input.reportValidity();
      }
    }
  });

  const initial = data.find(function (l) {
    return String(l.id) === hidden.value;
  });
  if (initial) select(initial);
})();
