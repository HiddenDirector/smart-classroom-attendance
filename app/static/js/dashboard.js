// Dashboard live updates: pipeline control, MJPEG feed, stats + table polling.
(function () {
  const toggleBtn = document.getElementById('pipeline-toggle');
  const spinner = document.getElementById('pipeline-spinner');
  const feed = document.getElementById('video-feed');
  const placeholder = document.getElementById('feed-placeholder');
  const motionBadge = document.getElementById('motion-badge');
  const eventList = document.getElementById('event-list');
  const todayTable = document.getElementById('today-table');

  let running = false;

  // ---------------------------------------------------------------- pipeline
  async function refreshStatus() {
    try {
      const res = await fetch('/api/pipeline/status');
      if (!res.ok) return;
      const status = await res.json();
      setRunning(status.running);
      renderMotion(status);
      renderEvents(status.events || []);
      if (status.last_error) showError(status.last_error);
    } catch (err) {
      /* server briefly unreachable — next poll will recover */
    }
  }

  function setRunning(value) {
    if (running === value) { toggleBtn.disabled = false; return; }
    running = value;
    toggleBtn.disabled = false;
    toggleBtn.className = running ? 'btn btn-danger' : 'btn btn-success';
    toggleBtn.innerHTML = running
      ? '<i class="bi bi-stop-fill"></i> Stop monitoring'
      : '<i class="bi bi-play-fill"></i> Start monitoring';
    if (running) {
      // Cache-busting param forces a fresh MJPEG connection.
      feed.src = '/video_feed?t=' + Date.now();
      feed.classList.remove('d-none');
      placeholder.classList.add('d-none');
    } else {
      feed.removeAttribute('src');
      feed.classList.add('d-none');
      placeholder.classList.remove('d-none');
      motionBadge.className = 'badge text-bg-secondary';
      motionBadge.textContent = 'offline';
    }
  }

  function renderMotion(status) {
    if (!status.running) return;
    if (status.motion_active) {
      motionBadge.className = 'badge text-bg-warning';
      motionBadge.textContent = 'motion — recognizing';
    } else {
      motionBadge.className = 'badge text-bg-success';
      motionBadge.textContent = 'idle';
    }
  }

  toggleBtn.addEventListener('click', async () => {
    toggleBtn.disabled = true;
    spinner.classList.remove('d-none');
    try {
      const res = await fetch(running ? '/api/pipeline/stop' : '/api/pipeline/start',
        { method: 'POST' });
      const body = await res.json();
      if (!res.ok) showError(body.error || 'Pipeline request failed.');
      await refreshStatus();
      await refreshStats();
    } catch (err) {
      showError('Could not reach the server.');
      toggleBtn.disabled = false;
    } finally {
      spinner.classList.add('d-none');
    }
  });

  function showError(message) {
    const existing = document.getElementById('pipeline-error');
    if (existing && existing.dataset.msg === message) return;
    existing?.remove();
    const div = document.createElement('div');
    div.id = 'pipeline-error';
    div.dataset.msg = message;
    div.className = 'alert alert-danger alert-dismissible fade show';
    div.innerHTML = `${message}
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
    document.querySelector('main').prepend(div);
  }

  // ----------------------------------------------------------------- events
  function renderEvents(events) {
    if (!events.length) return;
    eventList.innerHTML = events.map((e) => `
      <li class="list-group-item small event-${e.kind}">
        <span class="text-body-secondary me-2">${e.time}</span>${e.message}
      </li>`).join('');
  }

  // ------------------------------------------------------------ stats/table
  async function refreshStats() {
    try {
      const res = await fetch('/api/stats/today');
      if (!res.ok) return;
      const stats = await res.json();
      document.querySelectorAll('[data-stat]').forEach((el) => {
        el.textContent = stats[el.dataset.stat];
      });
    } catch (err) { /* retry on next poll */ }
  }

  async function refreshTable() {
    try {
      const res = await fetch('/api/attendance/today');
      if (!res.ok) return;
      const records = await res.json();
      todayTable.innerHTML = records.length ? records.map((r) => `
        <tr>
          <td>${r.time}</td>
          <td><span class="badge text-bg-light border">${escapeHtml(r.session)}</span></td>
          <td>${escapeHtml(r.roll_number)}</td>
          <td>${escapeHtml(r.full_name)}</td>
          <td class="d-none d-md-table-cell">${escapeHtml(r.department)}</td>
          <td><span class="badge text-bg-${r.status === 'Present' ? 'success' : 'warning'}">${r.status}</span></td>
          <td class="d-none d-sm-table-cell">${r.confidence_score !== null
            ? Math.round(r.confidence_score * 100) + '%'
            : '<span class="text-body-secondary">manual</span>'}</td>
        </tr>`).join('')
        : '<tr><td colspan="7" class="text-center text-body-secondary py-4">No attendance yet today.</td></tr>';
    } catch (err) { /* retry on next poll */ }
  }

  function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = String(value ?? '');
    return div.innerHTML;
  }

  // ------------------------------------------------------------------ boot
  refreshStatus();
  refreshStats();
  refreshTable();
  setInterval(refreshStatus, 2000);
  setInterval(() => { refreshStats(); refreshTable(); }, 5000);
})();
