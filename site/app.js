function escHtml(v) {
  return String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/**
 * Reclamation Evidence — Precision Earth Observation Platform (PEOP)
 * Institutional remote sensing operations, Leaflet GIS mapping, real-time cadastral intake,
 * pre-registered protocol validation, and enterprise B2B procurement engine.
 */

(function () {
  'use strict';

  // --- Sample 15-Site Pilot Well List for 1-Click Testing ---
  const SAMPLE_WELL_BATCH = [
    "01-06-018-26W4 (100)",
    "02-14-020-29W4 (100)",
    "04-12-014-20W4 (100)",
    "05-34-016-20W4 (102)",
    "06-20-029-19W4 (100)",
    "06-21-020-27W4 (Facility)",
    "08-10-029-26W4 (100)",
    "09-04-020-27W4 (102)",
    "10-23-018-20W4 (100)",
    "11-08-014-22W4 (Multi)",
    "11-14-017-21W4 (100)",
    "11-20-014-19W4 (100)",
    "12-16-014-19W4 (100)",
    "14-05-017-21W4 (102)",
    "16-03-017-21W4 (100)"
  ].join("\n");

  // --- Platform State ---
  const state = {
    activeView: 'dashboard',
    selectedPackage: 'pilot',
    orderPricing: {
      pilot: { name: 'Screening Pilot', price: 7500, sites: 15, weeks: 4 },
      benchmark: { name: 'Benchmark Check', price: 4800, sites: 15, weeks: 2 },
      portfolio: { name: 'Portfolio Screening', price: 18500, sites: 50, weeks: 8 }
    },
    parsedWells: [],
    mapInstance: null,
    mapMarkers: [],
    projects: [
      {
        id: 'PILOT-2026-0881',
        title: 'Sample Client A — Central Alberta Triage',
        licensee: 'Sample Client A (illustrative)',
        sitesCount: 15,
        fee: '$7,500 CAD',
        stage: 'validation',
        progress: 75,
        targetDate: 'Oct 24, 2026',
        tag: 'Blind Check Active',
        tagColor: 'blue'
      },
      {
        id: 'PILOT-2026-0742',
        title: 'Sample Client B — Legacy Portfolio Screen',
        licensee: 'Sample Client B (illustrative)',
        sitesCount: 27,
        fee: '$13,500 CAD',
        stage: 'ready',
        progress: 100,
        targetDate: 'Delivered Oct 4, 2026',
        tag: 'Register Handed Over',
        tagColor: 'emerald'
      },
      {
        id: 'BENCH-2026-0914',
        title: 'Sample Client C — Geospatial Blind Benchmark',
        licensee: 'Sample Client C (illustrative)',
        sitesCount: 15,
        fee: '$4,800 CAD',
        stage: 'processing',
        progress: 45,
        targetDate: 'Nov 02, 2026',
        tag: 'Month-matched S2 Ingest',
        tagColor: 'amber'
      },
      {
        id: 'ORD-2026-PILOT-9410',
        title: 'Sample Client D — Pilot Screen',
        licensee: 'Sample Client D (illustrative)',
        sitesCount: 15,
        fee: '$7,500 CAD',
        stage: 'intake',
        progress: 15,
        targetDate: 'Nov 14, 2026',
        tag: 'Pre-registering Protocol',
        tagColor: 'blue'
      }
    ],
    tasks: [
      { id: 1, text: 'Pre-register blind protocol with client', done: true, meta: 'Day 1 Milestone · Complete' },
      { id: 2, text: 'Sentinel-2 month-matched median-of-deltas ingestion', done: true, meta: '5-year baseline sync' },
      { id: 3, text: 'Phenology artifact filter & synthetic refutation check', done: false, meta: 'Prevents false recoveries' },
      { id: 4, text: 'Blind field data correlation & uncertainty CI', done: false, meta: 'Bootstrap 95% bounds' },
      { id: 5, text: 'Rank 15-site register & write validation memo', done: false, meta: 'Final handover packet' }
    ],
    calendarEvents: {
      12: { title: 'Sentinel-2 Satellite Overpass (Pass A)', type: 'satellite' },
      16: { title: 'Pilot Kickoff Milestone (Terms 50% Active)', type: 'milestone' },
      17: { title: 'Sentinel-2 Satellite Overpass (Pass B)', type: 'satellite' },
      22: { title: 'Sentinel-2 Satellite Overpass (Pass C)', type: 'satellite' },
      26: { title: 'Blind Field Data Review Sync', type: 'milestone' },
      30: { title: 'Synthetic Refutation QA Run', type: 'satellite' }
    },
    selectedCalDay: 16
  };

  // --- Toast Notification Helper ---
  function showToast(message) {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `<span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  }

  // --- DLS LSD Cadastral Parsing Engine ---
  const DLS_REGEX = /(?:(\d{3})\/)?(\d{1,2})-(\d{1,2})-(\d{1,3})-(\d{1,2})W([456])(?:\/(\d+))?/i;
  const WCSB_BOUNDS = { latMin: 49.0, latMax: 60.0, lonMin: -120.0, lonMax: -101.0 };

  function parseDls(dlsStr) {
    if (!dlsStr) return null;
    const m = dlsStr.trim().match(DLS_REGEX);
    if (!m) return null;
    const lsd = parseInt(m[2], 10);
    const sec = parseInt(m[3], 10);
    const twp = parseInt(m[4], 10);
    const rge = parseInt(m[5], 10);
    const mer = parseInt(m[6], 10);
    return {
      lsd,
      section: sec,
      township: twp,
      range: rge,
      meridian: mer,
      cleanDls: `${String(lsd).padStart(2, '0')}-${String(sec).padStart(2, '0')}-${String(twp).padStart(3, '0')}-${String(rge).padStart(2, '0')}W${mer}`
    };
  }

  function estimateCentroid(parsed) {
    if (!parsed) return null;
    const baseLons = { 4: -110.0, 5: -114.0, 6: -118.0 };
    const baseLon = baseLons[parsed.meridian] || -114.0;
    let lat = 49.0 + (parsed.township - 0.5) * 0.0869;
    let lon = baseLon - (parsed.range - 0.5) * 0.138;
    const lsdRow = Math.floor((parsed.lsd - 1) / 4);
    const lsdCol = (parsed.lsd - 1) % 4;
    lat += (lsdRow - 1.5) * 0.0036;
    lon -= (lsdCol - 1.5) * 0.0055;
    return {
      lat: Number(lat.toFixed(5)),
      lon: Number(lon.toFixed(5)),
      isValid: (lat >= WCSB_BOUNDS.latMin && lat <= WCSB_BOUNDS.latMax && lon >= WCSB_BOUNDS.lonMin && lon <= WCSB_BOUNDS.lonMax)
    };
  }

  function parseWellInputText(text) {
    const lines = text.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
    const results = [];
    lines.forEach((line, idx) => {
      const parsed = parseDls(line);
      if (parsed) {
        const centroid = estimateCentroid(parsed);
        results.push({
          index: idx + 1,
          raw: line,
          dls: parsed.cleanDls,
          lat: centroid ? centroid.lat : null,
          lon: centroid ? centroid.lon : null,
          valid: centroid ? centroid.isValid : false
        });
      } else {
        results.push({
          index: idx + 1,
          raw: line,
          dls: line,
          lat: null,
          lon: null,
          valid: false
        });
      }
    });
    return results;
  }

  // --- Interactive Leaflet Alberta Satellite Map ---
  function initAlbertaMap() {
    const mapEl = document.getElementById('alberta-satellite-map');
    if (!mapEl || typeof L === 'undefined') return;

    if (state.mapInstance) {
      state.mapInstance.remove();
    }

    // Centered over Central / Southern Alberta (Vulcan, Drumheller, Red Deer, Calgary corridor)
    state.mapInstance = L.map('alberta-satellite-map', {
      center: [51.25, -113.25],
      zoom: 7,
      zoomControl: true,
      attributionControl: false
    });

    // Esri World Imagery (High-res orbital satellite imagery without watermarks)
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 18,
      attribution: 'Tiles &copy; Esri'
    }).addTo(state.mapInstance);

    const sites = (window.RECLAMATION_LEDGER && window.RECLAMATION_LEDGER.sites) || [];
    state.mapMarkers = [];

    sites.forEach(site => {
      if (!site.lat || !site.lon) return;

      const isPos = site.delta >= 0.08;
      const isNeg = site.delta <= -0.08;
      const color = isPos ? '#10b981' : (isNeg ? '#ef4444' : '#2563eb');

      const marker = L.circleMarker([site.lat, site.lon], {
        radius: 6,
        fillColor: color,
        color: '#ffffff',
        weight: 1.5,
        opacity: 1,
        fillOpacity: 0.85
      }).addTo(state.mapInstance);

      const deltaFmt = (site.delta >= 0 ? '+' : '') + Number(site.delta).toFixed(2);
      marker.bindPopup(`
        <div style="font-family: var(--font-main); font-size: 12px; line-height: 1.4; color: #0f172a;">
          <div style="font-family: var(--font-mono); font-weight: 700; color: #1e3a8a;">${site.id}</div>
          <div>Delta: <strong style="color: ${color}; font-family: var(--font-mono);">${deltaFmt}</strong> (${site.stmt})</div>
          <div style="margin-top: 6px;">
            <button onclick="window.inspectSiteById('${site.id}')" style="background: #2563eb; color: white; border: none; border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight: 600; cursor: pointer;">
              Inspect Spectral Curve
            </button>
          </div>
        </div>
      `);

      state.mapMarkers.push(marker);
    });

    // Leaflet resize invalidation on view switch
    setTimeout(() => {
      if (state.mapInstance) state.mapInstance.invalidateSize();
    }, 200);
  }

  window.inspectSiteById = function(siteId) {
    const sites = (window.RECLAMATION_LEDGER && window.RECLAMATION_LEDGER.sites) || [];
    const site = sites.find(s => s.id === siteId);
    if (site) openSiteModal(site);
  };

  // --- View Switcher ---
  function initViewSwitcher() {
    const tabButtons = document.querySelectorAll('.view-tab-btn, .nav-item[data-view]');
    tabButtons.forEach(btn => {
      btn.addEventListener('click', (e) => {
        const targetView = btn.getAttribute('data-view');
        if (targetView) {
          e.preventDefault();
          switchView(targetView);
        }
      });
    });
  }

  function switchView(viewName) {
    state.activeView = viewName;
    document.querySelectorAll('.view-tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-view') === viewName);
    });
    document.querySelectorAll('.nav-item[data-view]').forEach(item => {
      item.classList.toggle('active', item.getAttribute('data-view') === viewName);
    });

    const panels = {
      dashboard: document.getElementById('view-dashboard'),
      order: document.getElementById('view-order'),
      kanban: document.getElementById('view-kanban'),
      ledger: document.getElementById('view-ledger'),
      method: document.getElementById('view-method')
    };

    Object.keys(panels).forEach(key => {
      if (panels[key]) {
        panels[key].style.display = (key === viewName || (viewName === 'dashboard' && key === 'dashboard')) ? 'block' : 'none';
      }
    });

    if (viewName === 'dashboard' && state.mapInstance) {
      setTimeout(() => state.mapInstance.invalidateSize(), 150);
    }

    if (viewName === 'order') {
      const orderEl = document.getElementById('order-intake-section');
      if (orderEl) orderEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  // --- Online Order & Intake Workflow ---
  function initOrderFlow() {
    const pkgCards = document.querySelectorAll('.pkg-option-card');
    pkgCards.forEach(card => {
      card.addEventListener('click', () => {
        pkgCards.forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');
        state.selectedPackage = card.getAttribute('data-pkg');
        updateOrderSummary();
      });
    });

    const wellTextarea = document.getElementById('well-intake-input');
    const loadSampleBtn = document.getElementById('btn-load-sample-wells');
    const parsedCountBadge = document.getElementById('parsed-well-count');

    function updateWells() {
      if (!wellTextarea) return;
      const text = wellTextarea.value;
      state.parsedWells = parseWellInputText(text);
      const validCount = state.parsedWells.filter(w => w.valid).length;
      if (parsedCountBadge) {
        parsedCountBadge.textContent = `✓ ${validCount} / ${state.parsedWells.length} Wells Validated (WCSB)`;
        if (validCount >= 15) {
          parsedCountBadge.style.background = 'var(--spectral-emerald-light)';
          parsedCountBadge.style.color = 'var(--spectral-emerald-text)';
        } else {
          parsedCountBadge.style.background = 'var(--spectral-amber-light)';
          parsedCountBadge.style.color = 'var(--spectral-amber-text)';
        }
      }
      updateOrderSummary();
    }

    if (wellTextarea) wellTextarea.addEventListener('input', updateWells);

    if (loadSampleBtn) {
      loadSampleBtn.addEventListener('click', () => {
        if (wellTextarea) {
          wellTextarea.value = SAMPLE_WELL_BATCH;
          updateWells();
          showToast('Loaded 15 sample Alberta ATS well LSDs for pilot scope');
        }
      });
    }

    const checkoutBtn = document.getElementById('btn-submit-order');
    if (checkoutBtn) checkoutBtn.addEventListener('click', handleOrderSubmission);
  }

  function updateOrderSummary() {
    const pkgInfo = state.orderPricing[state.selectedPackage] || state.orderPricing.pilot;
    const totalEl = document.getElementById('order-summary-total');
    const m1El = document.getElementById('milestone-kickoff-amt');
    const m2El = document.getElementById('milestone-handover-amt');

    const total = pkgInfo.price;
    const m1 = Math.round(total * 0.5);
    const m2 = total - m1;

    if (totalEl) totalEl.textContent = `$${total.toLocaleString()} CAD`;
    if (m1El) m1El.textContent = `$${m1.toLocaleString()} CAD`;
    if (m2El) m2El.textContent = `$${m2.toLocaleString()} CAD`;
  }

  function handleOrderSubmission(e) {
    if (e) e.preventDefault();
    const pkg = state.orderPricing[state.selectedPackage] || state.orderPricing.pilot;
    const wellCount = state.parsedWells.filter(w => w.valid).length || pkg.sites;
    const clientNameInput = document.getElementById('order-client-name');
    const companyInput = document.getElementById('order-company-name');
    const emailInput = document.getElementById('order-email');

    const clientName = (clientNameInput && clientNameInput.value.trim()) || 'Environmental Lead';
    const company = (companyInput && companyInput.value.trim()) || 'Obsidian Energy Ltd.';
    const email = (emailInput && emailInput.value.trim()) || 'closure-ops@wcsb-energy.ca';

    const orderId = `SOW-${new Date().getFullYear()}-PILOT-${Math.floor(1000 + Math.random() * 9000)}`;

    const newProject = {
      id: orderId,
      title: `${company} — ${pkg.name}`,
      licensee: company,
      sitesCount: wellCount,
      fee: `$${pkg.price.toLocaleString()} CAD`,
      stage: 'intake',
      progress: 15,
      targetDate: `4 Weeks from Kickoff`,
      tag: 'Pre-registered Scope',
      tagColor: 'blue'
    };

    state.projects.unshift(newProject);
    renderKanban();

    openOrderModal(newProject, clientName, email);
    showToast(`✓ Order ${orderId} generated! Pre-registration memo ready.`);
  }

  function openOrderModal(project, clientName, email) {
    const overlay = document.getElementById('order-success-modal');
    if (!overlay) return;

    const idEl = document.getElementById('modal-order-id');
    const detailsEl = document.getElementById('modal-order-details');
    if (idEl) idEl.textContent = project.id;
    if (detailsEl) {
      detailsEl.innerHTML = `
        <div style="background: var(--slate-50); border: 1px solid var(--slate-200); border-radius: 12px; padding: 18px; margin: 16px 0; font-size: 13px; line-height: 1.5;">
          <div style="display: flex; justify-content: space-between; border-bottom: 1px solid var(--slate-200); padding-bottom: 8px; margin-bottom: 8px;">
            <strong style="color: var(--navy);">Statement of Work / Order Specification</strong>
            <span style="font-family: var(--font-mono); font-size: 11px; color: var(--slate-500);">${new Date().toISOString().split('T')[0]}</span>
          </div>
          <p><strong>Licensee / Operator:</strong> ${project.licensee}</p>
          <p><strong>Lead Contact:</strong> ${clientName} (${email})</p>
          <p><strong>Scope:</strong> ${project.title} (${project.sitesCount} ATS Leases)</p>
          <p><strong>Fixed Fee:</strong> ${project.fee} + GST</p>
          <p><strong>Milestone Terms:</strong> 50% Kickoff ($3,750 CAD) upon protocol lock; 50% ($3,750 CAD) upon deliverable handover.</p>
          <p><strong>Deliverables:</strong> Ranked 15-site register, method packet, written blind validation memo.</p>
          <div style="margin-top: 10px; padding: 8px 12px; background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px; font-size: 11px; color: #92400e;">
            <strong>AER Regulatory Boundary:</strong> Screening triage only. No compliance certification, no contamination attribution, no replacement for field professional assessment.
          </div>
        </div>
      `;
    }

    overlay.classList.add('open');
  }

  // --- Kanban Board ---
  function renderKanban() {
    const cols = {
      intake: document.getElementById('kanban-col-intake'),
      processing: document.getElementById('kanban-col-processing'),
      validation: document.getElementById('kanban-col-validation'),
      ready: document.getElementById('kanban-col-ready')
    };

    Object.values(cols).forEach(col => { if (col) col.innerHTML = ''; });
    const counts = { intake: 0, processing: 0, validation: 0, ready: 0 };

    state.projects.forEach(p => {
      const targetCol = cols[p.stage] || cols.intake;
      counts[p.stage] = (counts[p.stage] || 0) + 1;

      if (targetCol) {
        const card = document.createElement('div');
        card.className = 'kanban-card';
        card.innerHTML = `
          <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px;">
            <span class="k-card-tag ${p.tagColor}">${p.tag}</span>
            <span style="font-family: var(--font-mono); font-size: 10px; color: var(--slate-400);">${p.id}</span>
          </div>
          <div class="k-card-title">${p.title}</div>
          <div class="k-card-desc">${p.sitesCount} Sites · ${p.fee}</div>
          <div style="background: var(--slate-100); height: 6px; border-radius: 3px; overflow: hidden; margin: 4px 0;">
            <div style="background: var(--primary); height: 100%; width: ${p.progress}%;"></div>
          </div>
          <div class="k-card-footer">
            <span>${p.targetDate}</span>
            <strong style="color: var(--navy); font-family: var(--font-mono);">${p.progress}%</strong>
          </div>
        `;
        targetCol.appendChild(card);
      }
    });

    ['intake', 'processing', 'validation', 'ready'].forEach(stage => {
      const countEl = document.getElementById(`count-${stage}`);
      if (countEl) countEl.textContent = counts[stage] || 0;
    });
  }

  // --- Calendar Widget ---
  function initCalendar() {
    const cells = document.querySelectorAll('.cal-day-cell:not(.inactive)');
    cells.forEach(cell => {
      const day = parseInt(cell.getAttribute('data-day'), 10);
      if (state.calendarEvents[day]) {
        cell.classList.add(state.calendarEvents[day].type === 'milestone' ? 'has-milestone' : 'has-event');
      }

      cell.addEventListener('click', () => {
        cells.forEach(c => c.classList.remove('active-selected'));
        cell.classList.add('active-selected');
        state.selectedCalDay = day;

        const event = state.calendarEvents[day];
        if (event) {
          showToast(`Oct ${day}: ${event.title}`);
        } else {
          showToast(`Oct ${day}, 2026: In-orbit Sentinel-2 overpass check.`);
        }
      });
    });
  }

  // --- Tasks Widget ---
  function initTasksWidget() {
    const taskListEl = document.getElementById('tasks-widget-list');
    if (!taskListEl) return;

    function renderTasks(filter = 'all') {
      taskListEl.innerHTML = '';
      state.tasks.forEach(task => {
        if (filter === 'active' && task.done) return;
        if (filter === 'completed' && !task.done) return;

        const item = document.createElement('div');
        item.className = `task-item ${task.done ? 'completed' : ''}`;
        item.innerHTML = `
          <input type="checkbox" id="task-${task.id}" ${task.done ? 'checked' : ''}>
          <div class="task-content">
            <div class="task-name">${task.text}</div>
            <div class="task-meta">${task.meta}</div>
          </div>
        `;

        const checkbox = item.querySelector('input[type="checkbox"]');
        checkbox.addEventListener('change', () => {
          task.done = checkbox.checked;
          item.classList.toggle('completed', task.done);
          showToast(`Milestone updated: ${task.done ? 'Verified' : 'Pending'}`);
        });

        taskListEl.appendChild(item);
      });
    }

    renderTasks();

    const createTaskBtn = document.getElementById('btn-create-task');
    if (createTaskBtn) {
      createTaskBtn.addEventListener('click', () => {
        const text = prompt('Enter task / field deliverable note:');
        if (text && text.trim()) {
          state.tasks.push({
            id: Date.now(),
            text: text.trim(),
            done: false,
            meta: 'Scheduled'
          });
          renderTasks();
          showToast('✓ Task created successfully');
        }
      });
    }
  }

  // --- Published counts: filled from ledger-data.js (generated from packets) ---
  function fillLedgerCounts() {
    const agg = (window.RECLAMATION_LEDGER && window.RECLAMATION_LEDGER.agg) || {};
    const tiers = agg.tiers || {};
    const values = {
      n_sites: agg.n_sites,
      n_detected: tiers.detected || 0,
      n_identified: tiers.identified || 0,
      n_high: (agg.confs || {}).high || 0
    };
    document.querySelectorAll('[data-ledger]').forEach(el => {
      const v = values[el.getAttribute('data-ledger')];
      if (v !== undefined) el.textContent = String(v);
    });
  }

  // --- Real 99-Packet Evidence Ledger Explorer ---
  function initLedgerTable() {
    const tableBody = document.getElementById('ledger-table-body');
    if (!tableBody) return;

    const sites = (window.RECLAMATION_LEDGER && window.RECLAMATION_LEDGER.sites) || [];
    if (!sites.length) return;

    let currentFilter = 'all';
    let searchQuery = '';

    function filterAndRender() {
      tableBody.innerHTML = '';
      const filtered = sites.filter(site => {
        const q = searchQuery.toLowerCase();
        const matchesSearch = !q || site.id.toLowerCase().includes(q);
        if (!matchesSearch) return false;

        if (currentFilter === 'detected') return site.tier === 'detected';
        if (currentFilter === 'identified') return site.tier === 'identified';
        if (currentFilter === 'high') return site.conf === 'high';
        return true;
      });

      filtered.slice(0, 30).forEach(site => {
        const tr = document.createElement('tr');
        const isPos = site.delta >= 0;
        const deltaFormatted = (isPos ? '+' : '') + Number(site.delta).toFixed(2);
        const ciStr = site.ci ? `[${(site.ci[0] >= 0 ? '+' : '') + site.ci[0].toFixed(2)}, ${(site.ci[1] >= 0 ? '+' : '') + site.ci[1].toFixed(2)}]` : 'Not estimated (<4 matched months)';

        tr.innerHTML = `
          <td><span class="site-id-mono">${site.id}</span></td>
          <td><span class="tier-badge ${site.tier}">${site.stmt}</span></td>
          <td><span class="delta-badge ${isPos ? 'pos' : 'neg'}">${deltaFormatted}</span></td>
          <td style="font-family: var(--font-mono); font-size: 11px; color: var(--slate-500);">${ciStr}</td>
          <td>
            <button class="btn-inspect-packet" data-id="${site.id}" style="background: var(--primary-light); color: var(--primary); border: none; padding: 4px 10px; border-radius: var(--radius-pill); font-size: 11px; font-weight: 700; cursor: pointer;">
              Inspect
            </button>
          </td>
        `;

        tr.querySelector('.btn-inspect-packet').addEventListener('click', () => {
          openSiteModal(site);
        });

        tableBody.appendChild(tr);
      });

      const countDisplay = document.getElementById('ledger-showing-count');
      if (countDisplay) {
        countDisplay.textContent = `Showing ${Math.min(filtered.length, 30)} of ${filtered.length} packets (${sites.length} total in public ledger)`;
      }
    }

    const pillBtns = document.querySelectorAll('.filter-pill-btn');
    pillBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        pillBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentFilter = btn.getAttribute('data-tier') || 'all';
        filterAndRender();
      });
    });

    const searchInputs = document.querySelectorAll('#global-search-input, #ledger-search-input');
    searchInputs.forEach(input => {
      input.addEventListener('input', (e) => {
        searchQuery = e.target.value.trim();
        filterAndRender();
      });
    });

    filterAndRender();
  }

  function openSiteModal(site) {
    const modal = document.getElementById('site-detail-modal');
    if (!modal) return;

    const titleEl = document.getElementById('modal-site-title');
    const contentEl = document.getElementById('modal-site-content');
    if (titleEl) titleEl.textContent = `Spectral Inspection: ${site.id}`;

    if (contentEl) {
      const isPos = site.delta >= 0;
      const deltaFormatted = (isPos ? '+' : '') + Number(site.delta).toFixed(4);
      const ciStr = site.ci ? `[${(site.ci[0] >= 0 ? '+' : '') + site.ci[0].toFixed(3)}, ${(site.ci[1] >= 0 ? '+' : '') + site.ci[1].toFixed(3)}]` : 'None (12 sites have no bootstrap interval)';

      // Generate a mini SVG time-series NDVI curve if observations exist
      let svgChart = '';
      if (site.obs && site.obs.length) {
        const points = site.obs.map((o, i) => {
          const x = 30 + (i / (site.obs.length - 1)) * 460;
          const y = 140 - ((o[1] - 0.1) / 0.8) * 110;
          return `${x},${y}`;
        }).join(' ');

        svgChart = `
          <div style="background: #0f172a; border-radius: 8px; padding: 12px; margin: 12px 0;">
            <div style="font-size: 11px; font-weight: 700; color: #94a3b8; font-family: var(--font-mono); margin-bottom: 6px;">
              Sentinel-2 NDVI Time-Series Trajectory (${site.obs.length} Clean Cloud-Free Passes)
            </div>
            <svg viewBox="0 0 520 160" style="width: 100%; height: 120px; overflow: visible;">
              <line x1="30" y1="140" x2="490" y2="140" stroke="#334155" stroke-width="1"></line>
              <line x1="30" y1="30" x2="490" y2="30" stroke="#334155" stroke-width="1" stroke-dasharray="3,3"></line>
              <polyline points="${points}" fill="none" stroke="#10b981" stroke-width="2.5"></polyline>
              <text x="30" y="24" fill="#94a3b8" font-size="10" font-family="monospace">Baseline Median: ${site.bmed}</text>
              <text x="320" y="24" fill="#60a5fa" font-size="10" font-family="monospace">Current Median: ${site.cmed}</text>
            </svg>
          </div>
        `;
      }

      contentEl.innerHTML = `
        <div style="display: flex; flex-direction: column; gap: 14px; font-size: 13px;">
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; background: var(--slate-50); padding: 14px; border-radius: 12px; border: 1px solid var(--slate-200);">
            <div><strong>Classification:</strong> <span class="tier-badge ${site.tier}">${site.stmt}</span> (Conf: ${site.conf})</div>
            <div><strong>Median Delta:</strong> <span class="delta-badge ${isPos ? 'pos' : 'neg'}">${deltaFormatted}</span></div>
            <div><strong>95% Bootstrap CI:</strong> ${ciStr}</div>
            <div><strong>Centroid Coordinates:</strong> ${site.lat.toFixed(4)} N, ${site.lon.toFixed(4)} W</div>
            <div><strong>Matched Months:</strong> May, Jun, Jul, Aug, Sep</div>
          </div>
          ${svgChart}
          <div>
            <strong>Validation Statement:</strong>
            <p style="color: var(--slate-700); margin-top: 4px;">${site.stmt}</p>
          </div>
          <div>
            <strong>Method Rationale:</strong>
            <p style="color: var(--slate-600); margin-top: 4px;">${site.rat}</p>
          </div>
          <div style="background: #fffbeb; border: 1px solid #fde68a; padding: 12px; border-radius: 8px;">
            <strong style="color: #92400e; font-size: 12px;">Stated Boundary & Caveats:</strong>
            <ul style="font-size: 11px; color: #78350f; margin-left: 16px; margin-top: 6px;">
              ${(site.cav || []).map(c => `<li>${escHtml(c)}</li>`).join('')}
            </ul>
          </div>
        </div>
      `;
    }

    modal.classList.add('open');
  }

  // --- Modals ---
  function initModals() {
    document.querySelectorAll('.modal-overlay').forEach(modal => {
      const closeBtn = modal.querySelector('.btn-close-modal');
      if (closeBtn) closeBtn.addEventListener('click', () => modal.classList.remove('open'));
      modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.classList.remove('open');
      });
    });
  }

  // --- Document Initialization ---
  document.addEventListener('DOMContentLoaded', () => {
    initAlbertaMap();
    initViewSwitcher();
    initOrderFlow();
    renderKanban();
    initCalendar();
    initTasksWidget();
    fillLedgerCounts();
    initLedgerTable();
    initModals();

    const wellTextarea = document.getElementById('well-intake-input');
    if (wellTextarea && !wellTextarea.value.trim()) {
      wellTextarea.value = SAMPLE_WELL_BATCH;
      wellTextarea.dispatchEvent(new Event('input'));
    }
  });

})();
