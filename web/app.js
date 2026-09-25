/* AutoRoster web frontend — hash-routed SPA over the JSON API.
 * Each view fetches its data, then renders the same Bootstrap markup the old
 * Django templates produced. */
'use strict';

/* ---------------------------------------------------------------- helpers */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (v) => String(v ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
// Django's truncatechars: at most n characters, the ellipsis included.
const trunc = (s, n) => { s = String(s ?? ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
// '?a=1&b=2' from the set values only; '' when none.
const qs = (params) => {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''));
  return q.toString() ? `?${q}` : '';
};
const plural = (n) => (n === 1 ? '' : 's');

let me = null; // signed-in user from /api/auth/me/

/* Django-messages equivalent: queued now, shown atop the next render. */
const flashes = [];
function flash(msg, tag = 'success') { flashes.push({ msg, tag }); }
function flashHtml() {
  const icon = { success: 'check-circle', danger: 'exclamation-circle' };
  return flashes.splice(0).map((f) => `
    <div class="alert alert-${f.tag} alert-dismissible fade show mb-3" role="alert">
      <i class="fas fa-${icon[f.tag] || 'info-circle'} me-2"></i>${esc(f.msg)}
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    </div>`).join('');
}

function render({ title, actions = '', body, docTitle }) {
  $('#page-title').textContent = title;
  $('#topbar-actions').innerHTML = actions;
  $('#main').innerHTML = flashHtml() + body;
  document.title = `${docTitle || title} | FTH Katsina`;
  window.scrollTo(0, 0);
}

function go(hash) {
  if (location.hash === hash) route();
  else location.hash = hash;
}

/* Field errors from a failed form post land in the form's [data-err=<field>]
 * slots; non-field errors, and any field without a slot, go to the
 * [data-err="__all__"] slot at the top. */
function showErrors(form, errors) {
  $$('[data-err]', form).forEach((el) => { el.innerHTML = ''; el.hidden = true; });
  $$('.is-invalid', form).forEach((el) => el.classList.remove('is-invalid'));
  const top = [];
  for (const [name, msgs] of Object.entries(errors || {})) {
    const input = form.elements[name];
    if (input?.classList) input.classList.add('is-invalid');
    const slot = name !== '__all__' && form.querySelector(`[data-err="${name}"]`);
    if (slot) {
      slot.innerHTML = msgs.map((m) => `<strong>${esc(m)}</strong>`).join('<br>');
      slot.hidden = false;
    } else {
      top.push(...msgs.map((m) => (name === '__all__' ? m : `${name.replace(/_/g, ' ')}: ${m}`)));
    }
  }
  const slot = form.querySelector('[data-err="__all__"]');
  if (slot && top.length) {
    slot.innerHTML = top.map(esc).join('<br>');
    slot.hidden = false;
    slot.scrollIntoView({ block: 'center' });
  }
}

/* Posts a form; field errors are shown in place, anything else is thrown. */
async function submitForm(form, path, body = new FormData(form)) {
  const btn = $('[type=submit]', form);
  if (btn) btn.disabled = true;
  try {
    return await Api.post(path, body);
  } catch (e) {
    if (!e.errors) throw e;
    showErrors(form, e.errors);
    return null;
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* One-line "loading" body while a view fetches. */
const loading = () => { $('#main').innerHTML = '<div class="text-center py-5 text-muted"><div class="spinner-border spinner-border-sm me-2"></div>Loading…</div>'; };

/* Pagination as the old templates drew it: « 1 2 [3] 4 5 » in a ±2 window. */
function pagerHtml(data, base, params) {
  if (data.num_pages <= 1) return '';
  const link = (n, text) => `<li class="page-item"><a class="page-link" href="#${base}${qs({ ...params, page: n })}">${text}</a></li>`;
  let items = data.page > 1 ? link(data.page - 1, '«') : '';
  for (let n = 1; n <= data.num_pages; n++) {
    if (n === data.page) items += `<li class="page-item active"><span class="page-link">${n}</span></li>`;
    else if (n > data.page - 3 && n < data.page + 3) items += link(n, n);
  }
  if (data.page < data.num_pages) items += link(data.page + 1, '»');
  return `<nav class="d-flex justify-content-center mt-3"><ul class="pagination pagination-sm">${items}</ul></nav>`;
}

/* A row of filter buttons. `keep` are the params that survive picking one of
 * these (the levels above it); lower levels are dropped. */
function filterBarHtml(label, base, params, key, keep, items, textOf, mb = 'mb-3') {
  const kept = Object.fromEntries(keep.map((k) => [k, params[k]]));
  const btn = (value, text) => {
    const on = (params[key] || '') === String(value ?? '');
    return `<a href="#${base}${qs({ ...kept, [key]: value })}" class="btn btn-sm ${on ? 'btn-primary' : 'btn-outline-secondary'}">${esc(text)}</a>`;
  };
  return `
    <div class="card ${mb}">
      <div class="card-body py-2 px-4">
        <div class="d-flex align-items-center gap-3 flex-wrap">
          <span style="font-weight:600;font-size:.875rem;color:#374151;">${label}</span>
          ${btn(null, 'All')}
          ${items.map((it) => btn(it.id, textOf(it))).join('')}
        </div>
      </div>
    </div>`;
}

const ACTION_BADGES = {
  created: ['#d1fae5', '#065f46', 'Created'],
  updated: ['#dbeafe', '#1e40af', 'Updated'],
  deleted: ['#fee2e2', '#991b1b', 'Deleted'],
  generated: ['#ede9fe', '#5b21b6', 'Generated'],
  exported: ['#fef3c7', '#92400e', 'Exported'],
};
function actionBadge(action) {
  const b = ACTION_BADGES[action];
  return b ? `<span class="badge" style="background:${b[0]};color:${b[1]};">${b[2]}</span>`
    : `<span class="badge bg-secondary">${esc(action)}</span>`;
}

const isAdmin = () => me?.is_admin;
const lookups = () => Api.get('/api/lookups/');

/* ------------------------------------------------------------------ shell */

function navHtml() {
  const link = (nav, href, icon, text) =>
    `<a href="#${href}" class="nav-link" data-nav="${nav}"><i class="fas fa-${icon}"></i> ${text}</a>`;
  return `
    <div class="nav-section-label">Main</div>
    ${link('dashboard', '/', 'chart-pie', 'Dashboard')}
    <div class="nav-section-label mt-2">Management</div>
    ${link('hospitals', '/hospitals', 'hospital-alt', 'Hospitals')}
    ${link('departments', '/departments', 'hospital', 'Departments')}
    ${link('units', '/units', 'layer-group', 'Units')}
    ${link('staff', '/staff', 'user-md', 'Staff')}
    <div class="nav-section-label mt-2">Roster</div>
    ${link('generate', '/rosters/generate', 'magic', 'Generate Roster')}
    ${link('rosters', '/rosters', 'list-alt', 'All Rosters')}
    <div class="nav-section-label mt-2">System</div>
    ${me.can_view_log ? link('activity', '/activity', 'history', 'Activity Log') : ''}
    ${me.is_admin ? link('access', '/activity/access', 'user-shield', 'Log Access') : ''}`;
}

function showShell() {
  document.body.classList.remove('auth-mode');
  $('#auth').innerHTML = '';
  $('#shell').hidden = false;
  $('#sidebar-nav').innerHTML = navHtml();
  $('#user-name').textContent = me.name;
  $('#user-phone').textContent = me.phone_number;
}

function showAuth() {
  document.body.classList.add('auth-mode');
  $('#shell').hidden = true;
  Idle.stop();
}

async function logout() {
  try { await Api.post('/api/auth/logout/'); } catch { /* already gone */ }
  me = null;
  go('#/login');
}

/* Sidebar: collapsed state remembered per browser; mobile starts collapsed. */
const Sidebar = (() => {
  const STORAGE_KEY = 'ar_sidebar_collapsed';
  const isMobile = () => window.innerWidth <= 768;
  function applyState(collapsed) {
    document.body.classList.toggle('sidebar-collapsed', collapsed);
    $('#sidebar-overlay').classList.toggle('active', !collapsed && isMobile());
  }
  function toggle() {
    const collapsed = !document.body.classList.contains('sidebar-collapsed');
    applyState(collapsed);
    try { localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0'); } catch { /* private mode */ }
  }
  function init() {
    let stored = null;
    try { stored = localStorage.getItem(STORAGE_KEY); } catch { /* private mode */ }
    applyState(stored !== null ? stored === '1' : isMobile());
    $('#sidebarToggle').addEventListener('click', toggle);
    $('#sidebarClose').addEventListener('click', toggle);
    $('#sidebar-overlay').addEventListener('click', toggle);
    // A page change used to reload the page; on a phone that closed the drawer.
    $('#sidebar-nav').addEventListener('click', (e) => { if (e.target.closest('a') && isMobile()) applyState(true); });
  }
  return { init };
})();

/* Auto-logout after 30 idle minutes, with a 60s warning — the server session
 * (SESSION_COOKIE_AGE) lasts the same 30 minutes. */
const Idle = (() => {
  const IDLE_LIMIT = 30 * 60 * 1000;
  const WARN_BEFORE = 60 * 1000;
  let lastActivity = Date.now();
  let checkInterval = null;
  let countdownInterval = null;
  let modal = null;

  function reset() {
    lastActivity = Date.now();
    if (modal && $('#idleWarningModal').classList.contains('show')) {
      modal.hide();
      clearInterval(countdownInterval);
    }
  }
  function expire() {
    stop();
    modal.hide();
    logout();
  }
  function check() {
    const remaining = IDLE_LIMIT - (Date.now() - lastActivity);
    if (remaining <= 0) return expire();
    if (remaining > WARN_BEFORE || $('#idleWarningModal').classList.contains('show')) return;
    modal.show();
    let secs = Math.ceil(remaining / 1000);
    $('#idleCountdown').textContent = secs;
    clearInterval(countdownInterval);
    countdownInterval = setInterval(() => {
      secs -= 1;
      $('#idleCountdown').textContent = Math.max(secs, 0);
      if (secs <= 0) expire();
    }, 1000);
  }
  function start() {
    stop();
    lastActivity = Date.now();
    checkInterval = setInterval(check, 5000);
  }
  function stop() {
    clearInterval(checkInterval);
    clearInterval(countdownInterval);
  }
  function init() {
    modal = new bootstrap.Modal($('#idleWarningModal'));
    ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll', 'click'].forEach((ev) =>
      document.addEventListener(ev, reset, { passive: true }));
    $('#idleStayBtn').addEventListener('click', () => { reset(); Api.get('/api/auth/me/').catch(() => {}); });
    $('#idleLogoutBtn').addEventListener('click', () => { modal.hide(); stop(); logout(); });
  }
  return { init, start, stop };
})();

/* ------------------------------------------------------------ auth views */

function authCard(body) {
  showAuth();
  document.title = 'Login | AutoRoster';
  $('#auth').innerHTML = `
    <div class="login-card">
      <div class="login-header">
        <div class="login-logo"><i class="fas fa-calendar-alt"></i></div>
        <h4>AutoRoster</h4>
        <p>Federal Teaching Hospital Katsina<br>Pharmacy Department</p>
      </div>
      <div class="login-body">${body}
        <p class="hospital-tag mt-2 mb-0">
          <i class="fas fa-shield-alt me-1"></i>Secure access — authorized personnel only
        </p>
      </div>
    </div>`;
}

const authInput = (name, label, icon, type, placeholder, extra = '') => `
  <div class="mb-3">
    <label class="form-label">${label}</label>
    <div class="input-group">
      <span class="input-group-text"><i class="fas fa-${icon}"></i></span>
      <input type="${type}" name="${name}" class="form-control" placeholder="${placeholder}" ${extra}>
    </div>
    <div class="invalid-feedback" style="display:block" data-err="${name}" hidden></div>
  </div>`;

async function signedIn(user) {
  me = user;
  showShell();
  Idle.start();
  go(sessionStorage.getItem('next') || '#/');
  sessionStorage.removeItem('next');
}

function viewLogin() {
  authCard(`
    <form id="loginForm">
      <div class="alert alert-danger mb-4" data-err="__all__" hidden></div>
      ${authInput('phone_number', 'Phone Number', 'phone', 'text', 'e.g. 08032194090', 'autofocus required')}
      <div class="mb-4">${authInput('password', 'Password', 'lock', 'password', 'Enter password', 'required')}</div>
      <button type="submit" class="btn btn-login">
        <i class="fas fa-sign-in-alt me-2"></i>Sign In
      </button>
    </form>
    <p class="login-link">No account? <a href="#/register">Register</a></p>`);
  const form = $('#loginForm');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const user = await submitForm(form, '/api/auth/login/');
      if (user) signedIn(user);
    } catch (err) {
      showErrors(form, { __all__: [err.message] });
    }
  });
}

function viewRegister() {
  authCard(`
    <form id="registerForm" novalidate>
      <div class="alert alert-danger mb-4" data-err="__all__" hidden></div>
      ${authInput('phone_number', 'Phone Number', 'phone', 'text', 'e.g. 08032194090', 'autofocus required')}
      ${authInput('full_name', 'Full Name <span class="text-muted fw-normal">(optional)</span>', 'user', 'text', 'e.g. Amina Yusuf')}
      ${authInput('password1', 'Password', 'lock', 'password', 'Min. 8 characters', 'required')}
      <div class="mb-4">${authInput('password2', 'Confirm Password', 'lock', 'password', 'Repeat password', 'required')}</div>
      <button type="submit" class="btn btn-login">
        <i class="fas fa-user-plus me-2"></i>Create Account
      </button>
    </form>
    <p class="login-link">Already have an account? <a href="#/login">Sign in</a></p>`);
  const form = $('#registerForm');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const user = await submitForm(form, '/api/auth/register/');
      if (user) signedIn(user);
    } catch (err) {
      showErrors(form, { __all__: [err.message] });
    }
  });
}

/* -------------------------------------------------------------- dashboard */

async function viewDashboard() {
  const d = await Api.get('/api/dashboard/');
  const stat = (bg, icon, value, label) => `
    <div class="col-md-3">
      <div class="stat-card" style="background: linear-gradient(135deg, ${bg});">
        <div class="stat-icon"><i class="fas fa-${icon}"></i></div>
        <div>
          <div class="stat-value">${value}</div>
          <div class="stat-label">${label}</div>
        </div>
      </div>
    </div>`;
  const cardHeader = (icon, text, href) => `
    <div class="card-header d-flex align-items-center justify-content-between" style="background:#fff; border-bottom:2px solid #e8f0f7;">
      <span style="color:#1B4F72;"><i class="fas fa-${icon} me-2"></i>${text}</span>
      <a href="#${href}" class="btn btn-outline-primary btn-sm">View All</a>
    </div>`;
  const th = (t) => `<th style="font-size:.75rem;color:#6b7280;font-weight:600;padding:10px 16px;">${t}</th>`;

  render({
    title: 'Dashboard',
    actions: `<a href="#/rosters/generate" class="btn btn-primary btn-sm"><i class="fas fa-magic me-1"></i> Generate Roster</a>`,
    body: `
      <div class="row g-3 mb-4">
        ${stat('#0d6efd, #0a58ca', 'hospital-alt', d.total_hospitals, 'Hospitals')}
        ${stat('#1B4F72, #2E86C1', 'layer-group', d.total_units, `Units <small style="font-size:.7rem;opacity:.75;">(${d.total_departments} depts)</small>`)}
        ${stat('#1e7e5a, #27ae60', 'user-md', d.total_staff, 'Active Staff')}
        ${stat('#7d3c98, #a569bd', 'calendar-check', d.total_rosters, 'Rosters Generated')}
      </div>

      <div class="row g-3 mb-3">
        <div class="col-12">
          <div class="card">
            ${cardHeader('history', 'Recent Activity', '/activity')}
            <div class="card-body p-0">
              ${d.recent_activity.length ? `
              <table class="table table-hover mb-0"><tbody>
                ${d.recent_activity.map((log) => `
                <tr>
                  <td style="width:130px;font-size:.78rem;color:#6b7280;white-space:nowrap;padding:8px 16px;">${esc(log.time)}</td>
                  <td style="width:140px;font-size:.875rem;font-weight:500;padding:8px 10px;">${esc(log.user || '—')}</td>
                  <td style="width:90px;padding:8px 10px;">${actionBadge(log.action)}</td>
                  <td style="font-size:.8rem;color:#1B4F72;padding:8px 10px;">${esc(log.object_type)}</td>
                  <td style="font-size:.875rem;padding:8px 16px;">${esc(trunc(log.object_str, 60))}</td>
                </tr>`).join('')}
              </tbody></table>` : '<div class="text-center py-3 text-muted"><small>No activity yet.</small></div>'}
            </div>
          </div>
        </div>
      </div>

      <div class="row g-3">
        <div class="col-md-7">
          <div class="card h-100">
            ${cardHeader('list-alt', 'Recent Rosters', '/rosters')}
            <div class="card-body p-0">
              ${d.recent_rosters.length ? `
              <table class="table table-hover mb-0">
                <thead><tr style="background:#f8fafc;">${th('ROSTER')}${th('UNIT')}${th('PERIOD')}${th('')}</tr></thead>
                <tbody>
                  ${d.recent_rosters.map((r) => `
                  <tr>
                    <td style="font-size:.875rem;">${esc(trunc(r.roster_title, 30))}</td>
                    <td style="font-size:.875rem;">${esc(trunc(r.unit_name, 25))}</td>
                    <td><span class="badge" style="background:#e8f0f7;color:#1B4F72;font-weight:600;">${esc(r.period)}</span></td>
                    <td><a href="#/rosters/${r.id}" class="btn btn-sm btn-outline-primary py-0 px-2"><i class="fas fa-eye"></i></a></td>
                  </tr>`).join('')}
                </tbody>
              </table>` : `
              <div class="text-center py-5 text-muted">
                <i class="fas fa-calendar-times fa-3x mb-3 opacity-25"></i>
                <p>No rosters yet. <a href="#/rosters/generate">Generate one</a>.</p>
              </div>`}
            </div>
          </div>
        </div>

        <div class="col-md-5">
          <div class="card mb-3">
            <div class="card-header" style="background:#fff; border-bottom:2px solid #e8f0f7; color:#1B4F72;">
              <i class="fas fa-bolt me-2"></i>Quick Actions
            </div>
            <div class="card-body d-grid gap-2">
              <a href="#/rosters/generate" class="btn btn-primary"><i class="fas fa-magic me-2"></i>Generate New Roster</a>
              <a href="#/staff/new" class="btn btn-outline-primary"><i class="fas fa-user-plus me-2"></i>Add Staff Member</a>
              <a href="#/departments/new" class="btn btn-outline-secondary"><i class="fas fa-plus-circle me-2"></i>Add Department</a>
              <a href="#/units/new" class="btn btn-outline-secondary"><i class="fas fa-layer-group me-2"></i>Add Unit</a>
              <a href="#/hospitals/new" class="btn btn-outline-secondary"><i class="fas fa-hospital-alt me-2"></i>Add Hospital</a>
            </div>
          </div>

          <div class="card">
            <div class="card-header" style="background:#fff; border-bottom:2px solid #e8f0f7; color:#1B4F72;">
              <i class="fas fa-hospital me-2"></i>Departments
            </div>
            <div class="card-body p-0">
              ${d.departments.length ? `
              <ul class="list-group list-group-flush">
                ${d.departments.map((dept) => `
                <li class="list-group-item px-4 py-2" style="font-size:.875rem;">
                  <div class="d-flex justify-content-between align-items-center">
                    <div style="font-weight:600;color:#1B4F72;">${esc(dept.department_name)}</div>
                    <span class="badge" style="background:#e8f0f7;color:#1B4F72;">${dept.active_staff_count} staff</span>
                  </div>
                  ${dept.units.map((u) => `<small class="text-muted d-block ms-2"><i class="fas fa-layer-group me-1" style="font-size:.65rem;"></i>${esc(trunc(u, 40))}</small>`).join('')}
                </li>`).join('')}
              </ul>` : `
              <div class="text-center py-4 text-muted">
                <small>No departments. <a href="#/departments/new">Add one</a>.</small>
              </div>`}
            </div>
          </div>
        </div>
      </div>`,
  });
}

/* ------------------------------------------------------- simple CRUD forms */

/* Hospital, department and unit forms: a centred card, one field per row,
 * laid out as crispy-forms drew them. */
function simpleFormHtml(title, icon, fields, submit, back, backLabel) {
  const field = (f) => {
    const req = f.required ? '<span class="asteriskField">*</span>' : '';
    const control = f.options
      ? `<select name="${f.name}" id="id_${f.name}" class="select form-select" ${f.required ? 'required' : ''}>
           <option value="">---------</option>
           ${f.options.map((o) => `<option value="${o.id}" ${String(o.id) === String(f.value ?? '') ? 'selected' : ''}>${esc(o.str)}</option>`).join('')}
         </select>`
      : `<input type="text" name="${f.name}" id="id_${f.name}" class="textinput form-control" maxlength="${f.maxlength}"
           placeholder="${esc(f.placeholder)}" value="${esc(f.value ?? '')}" ${f.required ? 'required' : ''}>`;
    return `
      <div id="div_id_${f.name}" class="mb-3">
        <label for="id_${f.name}" class="form-label${f.required ? ' requiredField' : ''}">${f.label}${req}</label>
        ${control}
        <span class="invalid-feedback" style="display:block" data-err="${f.name}" hidden></span>
      </div>`;
  };
  return `
    <div class="row justify-content-center">
      <div class="col-md-6">
        <div class="card">
          <div class="card-header" style="background:#1B4F72;color:#fff;">
            <i class="fas fa-${icon} me-2"></i>${title}
          </div>
          <div class="card-body p-4">
            <form id="objForm">
              <div class="alert alert-block alert-danger" data-err="__all__" hidden></div>
              ${fields.map(field).join('')}
              <input type="submit" name="submit" value="${submit}" class="btn btn-primary mt-3">
            </form>
          </div>
        </div>
        <div class="mt-3">
          <a href="#${back}" class="text-muted text-decoration-none">
            <i class="fas fa-arrow-left me-1"></i> Back to ${backLabel}
          </a>
        </div>
      </div>
    </div>`;
}

/* Wires a create/edit form: POST to the collection or the record, then flash
 * and go back to the list, as the old views redirected. */
function wireObjForm(form, { path, id, noun, back }) {
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const saved = await submitForm(form, id ? `${path}${id}/` : path);
    if (!saved) return;
    flash(`${noun} ${id ? 'updated' : 'created'}.`);
    go(`#${back}`);
  });
}

async function viewHospitalForm(id) {
  const h = id ? await Api.get(`/api/hospitals/${id}/`) : {};
  const title = id ? 'Edit Hospital' : 'Add Hospital';
  render({
    title,
    body: simpleFormHtml(title, 'hospital-alt', [
      { name: 'name', label: 'Name', required: true, maxlength: 200, placeholder: 'e.g. FEDERAL TEACHING HOSPITAL KATSINA', value: h.name },
      { name: 'address', label: 'Address', maxlength: 300, placeholder: 'e.g. Hospital Road, Katsina', value: h.address },
    ], 'Save Hospital', '/hospitals', 'Hospitals'),
  });
  wireObjForm($('#objForm'), { path: '/api/hospitals/', id, noun: 'Hospital', back: '/hospitals' });
}

async function viewDepartmentForm(id, params) {
  const [lk, d] = await Promise.all([lookups(), id ? Api.get(`/api/departments/${id}/`) : { hospital: params.hospital }]);
  const title = id ? 'Edit Department' : 'Add Department';
  render({
    title,
    body: simpleFormHtml(title, 'hospital', [
      { name: 'hospital', label: 'Hospital', required: true, options: lk.hospitals, value: d.hospital },
      { name: 'department_name', label: 'Department name', required: true, maxlength: 200, placeholder: 'e.g. PHARMACY DEPARTMENT',
        value: id ? d.department_name : 'PHARMACY DEPARTMENT' },
    ], 'Save Department', '/departments', 'Departments'),
  });
  wireObjForm($('#objForm'), { path: '/api/departments/', id, noun: 'Department', back: '/departments' });
}

async function viewUnitForm(id, params) {
  const [lk, u] = await Promise.all([lookups(), id ? Api.get(`/api/units/${id}/`) : { department: params.dept }]);
  const title = id ? 'Edit Unit' : 'Add Unit';
  render({
    title,
    body: simpleFormHtml(title, 'layer-group', [
      { name: 'department', label: 'Department', required: true, options: lk.departments, value: u.department },
      { name: 'unit_name', label: 'Unit name', required: true, maxlength: 200, placeholder: 'e.g. ACCIDENT AND EMERGENCY PHARMACY UNIT', value: u.unit_name },
    ], 'Save Unit', '/units', 'Units'),
  });
  wireObjForm($('#objForm'), { path: '/api/units/', id, noun: 'Unit', back: '/units' });
}

/* ------------------------------------------------------ confirm deletion */

const DELETABLE = {
  hospitals: { label: 'Hospital', done: 'Hospital deleted.' },
  departments: { label: 'Department', done: 'Department deleted.' },
  units: { label: 'Unit', done: 'Unit deleted.' },
  staff: { label: 'Staff', done: 'Staff member deleted.' },
  rosters: { label: 'Roster', done: 'Roster deleted.' },
};

async function viewDelete(type, id) {
  const { label, done } = DELETABLE[type];
  const obj = await Api.get(`/api/${type}/${id}/`);
  render({
    title: `Delete ${label}`,
    body: `
      <div class="row justify-content-center">
        <div class="col-md-5">
          <div class="card" style="border-top:4px solid #dc2626;">
            <div class="card-body text-center p-5">
              <div style="width:64px;height:64px;background:#fee2e2;border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 20px;">
                <i class="fas fa-trash-alt fa-2x" style="color:#dc2626;"></i>
              </div>
              <h5 style="font-weight:700;color:#1a202c;">Delete ${label}?</h5>
              <p class="text-muted mb-4">
                You are about to delete <strong>${esc(obj.str)}</strong>.<br>
                This action cannot be undone.
              </p>
              <div class="d-flex gap-3 justify-content-center">
                <button type="button" class="btn btn-danger px-4" id="confirmDelete">
                  <i class="fas fa-trash me-1"></i> Yes, Delete
                </button>
                <button type="button" class="btn btn-outline-secondary px-4" onclick="history.back()">Cancel</button>
              </div>
            </div>
          </div>
        </div>
      </div>`,
  });
  $('#confirmDelete').addEventListener('click', async (e) => {
    e.currentTarget.disabled = true;
    await Api.del(`/api/${type}/${id}/`);
    flash(done);
    go(`#/${type}`);
  });
}

/* -------------------------------------------------------------- hospitals */

const iconTile = (icon, size = 44, extra = '') => `
  <div style="width:${size}px;height:${size}px;background:#e8f0f7;border-radius:10px;display:flex;align-items:center;justify-content:center;">
    <i class="fas fa-${icon}" style="color:#1B4F72;${extra}"></i>
  </div>`;

const dropdownHtml = (items) => `
  <div class="dropdown">
    <button class="btn btn-sm btn-light" data-bs-toggle="dropdown"><i class="fas fa-ellipsis-v"></i></button>
    <ul class="dropdown-menu dropdown-menu-end">${items.map((it) => (it === '-'
      ? '<li><hr class="dropdown-divider"></li>'
      : `<li><a class="dropdown-item${it.danger ? ' text-danger' : ''}" href="#${it.href}"><i class="fas fa-${it.icon} me-2"></i>${it.text}</a></li>`)).join('')}
    </ul>
  </div>`;

const emptyState = (icon, title, extra = '') => `
  <div class="col-12 text-center py-5">
    <i class="fas fa-${icon} fa-4x text-muted opacity-25 mb-3"></i>
    <h5 class="text-muted">${title}</h5>
    ${extra}
  </div>`;

async function viewHospitals(m, params) {
  const data = await Api.get('/api/hospitals/', { page: params.page });
  const admin = isAdmin();
  render({
    title: 'Hospitals',
    actions: admin ? `<a href="#/hospitals/new" class="btn btn-primary btn-sm"><i class="fas fa-plus me-1"></i> Add Hospital</a>` : '',
    body: `
      <div class="row g-3">
        ${data.results.map((h) => `
        <div class="col-md-6 col-lg-4">
          <div class="card h-100">
            <div class="card-body">
              <div class="d-flex align-items-start justify-content-between mb-3">
                <div class="d-flex align-items-center gap-2">
                  ${iconTile('hospital-alt', 44, 'font-size:1.1rem;')}
                  <div>
                    <a href="#/hospitals/${h.id}" style="font-weight:700;font-size:.95rem;color:#1B4F72;text-decoration:none;">${esc(h.name)}</a>
                    ${h.address ? `<small class="text-muted">${esc(trunc(h.address, 40))}</small>` : ''}
                  </div>
                </div>
                ${admin ? dropdownHtml([
                  { href: `/hospitals/${h.id}/edit`, icon: 'edit', text: 'Edit' },
                  { href: `/hospitals/${h.id}/delete`, icon: 'trash', text: 'Delete', danger: true },
                ]) : ''}
              </div>
              <div class="d-flex gap-3 mb-3">
                <div class="text-center">
                  <div style="font-size:1.3rem;font-weight:700;color:#1B4F72;">${h.dept_count}</div>
                  <small class="text-muted">Departments</small>
                </div>
                <div class="text-center">
                  <div style="font-size:1.3rem;font-weight:700;color:#27ae60;">${h.staff_count}</div>
                  <small class="text-muted">Staff</small>
                </div>
              </div>
              ${h.departments.length ? `
              <div style="font-size:.8rem;color:#6b7280;">
                ${h.departments.map((n) => `<span class="badge me-1 mb-1" style="background:#e8f0f7;color:#1B4F72;">${esc(n)}</span>`).join('')}
                ${h.dept_count > 3 ? `<span class="text-muted">+${h.dept_count - 3} more</span>` : ''}
              </div>` : ''}
            </div>
            <div class="card-footer bg-transparent d-flex gap-2">
              <a href="#/departments?hospital=${h.id}" class="btn btn-outline-primary btn-sm flex-fill"><i class="fas fa-hospital me-1"></i> Departments</a>
              ${admin ? `<a href="#/departments/new?hospital=${h.id}" class="btn btn-primary btn-sm flex-fill"><i class="fas fa-plus me-1"></i> Add Dept</a>` : ''}
            </div>
          </div>
        </div>`).join('') || emptyState('hospital-alt', 'No hospitals yet',
          `<a href="#/hospitals/new" class="btn btn-primary mt-2"><i class="fas fa-plus me-1"></i> Add First Hospital</a>`)}
      </div>
      ${pagerHtml(data, '/hospitals', {})}`,
  });
}

async function viewHospital(id) {
  const h = await Api.get(`/api/hospitals/${id}/`);
  const admin = isAdmin();
  const xs = (href, cls, icon, text, title) =>
    `<a href="#${href}" class="btn btn-xs ${cls} py-0 px-2" style="font-size:.75rem;" title="${title}"><i class="fas fa-${icon}${text ? ' me-1' : ''}"></i>${text ? ` ${text}` : ''}</a>`;
  render({
    title: h.name,
    actions: `
      ${admin ? `
      <a href="#/hospitals/${h.id}/edit" class="btn btn-outline-secondary btn-sm"><i class="fas fa-edit me-1"></i> Edit Hospital</a>
      <a href="#/departments/new?hospital=${h.id}" class="btn btn-primary btn-sm"><i class="fas fa-plus me-1"></i> Add Department</a>` : ''}
      <a href="#/hospitals" class="btn btn-light btn-sm"><i class="fas fa-arrow-left me-1"></i> All Hospitals</a>`,
    body: `
      <div class="section-card mb-4">
        <div class="d-flex align-items-center gap-3">
          <div style="width:56px;height:56px;background:#e8f0f7;border-radius:12px;display:flex;align-items:center;justify-content:center;">
            <i class="fas fa-hospital-alt fa-lg" style="color:#1B4F72;"></i>
          </div>
          <div>
            <h5 class="mb-0 fw-bold" style="color:#1B4F72;">${esc(h.name)}</h5>
            ${h.address ? `<small class="text-muted"><i class="fas fa-map-marker-alt me-1"></i>${esc(h.address)}</small>` : ''}
          </div>
          <div class="ms-auto d-flex gap-4 text-center">
            <div>
              <div style="font-size:1.6rem;font-weight:700;color:#1B4F72;">${h.departments.length}</div>
              <small class="text-muted">Departments</small>
            </div>
          </div>
        </div>
      </div>

      ${h.departments.map((d) => `
      <div class="section-card mb-3">
        <div class="d-flex align-items-center justify-content-between mb-3">
          <div class="d-flex align-items-center gap-2">
            <i class="fas fa-hospital" style="color:#2E86C1;"></i>
            <h6 class="mb-0">${esc(d.department_name)}</h6>
            <span class="badge ms-1" style="background:#e8f0f7;color:#1B4F72;">${d.unit_count} unit${plural(d.unit_count)}</span>
            <span class="badge" style="background:#d1fae5;color:#065f46;">${d.staff_count} active staff</span>
          </div>
          ${admin ? `
          <div class="d-flex gap-2">
            <a href="#/units/new?dept=${d.id}" class="btn btn-sm btn-outline-primary"><i class="fas fa-plus me-1"></i> Add Unit</a>
            <a href="#/departments/${d.id}/edit" class="btn btn-sm btn-outline-secondary"><i class="fas fa-edit"></i></a>
            <a href="#/departments/${d.id}/delete" class="btn btn-sm btn-outline-danger"><i class="fas fa-trash"></i></a>
          </div>` : ''}
        </div>
        ${d.units.length ? `
        <div class="table-responsive">
          <table class="table table-modern table-hover mb-0">
            <thead><tr><th>Unit Name</th><th class="text-center">Active Staff</th><th class="text-center">Rosters</th><th class="text-end">Actions</th></tr></thead>
            <tbody>
              ${d.units.map((u) => `
              <tr>
                <td><i class="fas fa-layer-group me-2 text-muted"></i><strong>${esc(u.unit_name)}</strong></td>
                <td class="text-center"><span class="badge" style="background:#e8f0f7;color:#1B4F72;">${u.staff_count}</span></td>
                <td class="text-center"><span class="badge" style="background:#f3e8ff;color:#7c3aed;">${u.roster_count}</span></td>
                <td class="text-end">
                  <div class="d-flex gap-1 justify-content-end">
                    ${xs(`/staff?unit=${u.id}`, 'btn-outline-primary', 'users', 'Staff', 'View staff')}
                    ${xs(`/rosters?unit=${u.id}`, 'btn-outline-secondary', 'list-alt', 'Rosters', 'View rosters')}
                    ${admin ? xs(`/units/${u.id}/edit`, 'btn-outline-secondary', 'edit', '', 'Edit unit')
                      + xs(`/units/${u.id}/delete`, 'btn-outline-danger', 'trash', '', 'Delete unit') : ''}
                  </div>
                </td>
              </tr>`).join('')}
            </tbody>
          </table>
        </div>` : `
        <p class="text-muted mb-0" style="font-size:.875rem;">
          <i class="fas fa-info-circle me-1"></i> No units yet.
          ${admin ? `<a href="#/units/new?dept=${d.id}">Add one</a>` : ''}
        </p>`}
      </div>`).join('') || `
      <div class="text-center py-5">
        <i class="fas fa-hospital fa-4x text-muted opacity-25 mb-3"></i>
        <h5 class="text-muted">No departments yet</h5>
        ${admin ? `<a href="#/departments/new?hospital=${h.id}" class="btn btn-primary mt-2"><i class="fas fa-plus me-1"></i> Add First Department</a>` : ''}
      </div>`}`,
  });
}

/* ------------------------------------------------------------ departments */

async function viewDepartments(m, params) {
  const [data, lk] = await Promise.all([Api.get('/api/departments/', params), lookups()]);
  const admin = isAdmin();
  render({
    title: 'Departments',
    actions: admin ? `<a href="#/departments/new" class="btn btn-primary btn-sm"><i class="fas fa-plus me-1"></i> Add Department</a>` : '',
    body: `
      ${filterBarHtml('Filter by Hospital:', '/departments', params, 'hospital', [], lk.hospitals, (h) => trunc(h.name, 30), 'mb-4')}
      <div class="row g-3">
        ${data.results.map((d) => `
        <div class="col-md-6 col-lg-4">
          <div class="card h-100">
            <div class="card-body">
              <div class="d-flex align-items-start justify-content-between mb-2">
                <div class="d-flex align-items-center gap-2">
                  ${iconTile('hospital-alt', 40)}
                  <div>
                    <div style="font-weight:700;font-size:.9rem;color:#1B4F72;">${esc(d.department_name)}</div>
                    <small class="text-muted">${esc(trunc(d.hospital_name, 30))}</small>
                  </div>
                </div>
                ${admin ? dropdownHtml([
                  { href: `/departments/${d.id}/edit`, icon: 'edit', text: 'Edit' },
                  { href: `/units/new?dept=${d.id}`, icon: 'plus', text: 'Add Unit' },
                  '-',
                  { href: `/departments/${d.id}/delete`, icon: 'trash', text: 'Delete', danger: true },
                ]) : ''}
              </div>
              ${d.units.length ? `
              <div class="mb-2">
                ${d.units.map((u) => `
                <div class="d-flex align-items-center justify-content-between px-2 py-1 mb-1 rounded" style="background:#f8fafc;font-size:.8rem;">
                  <span style="color:#374151;"><i class="fas fa-layer-group me-1 text-muted"></i>${esc(trunc(u.unit_name, 35))}</span>
                  <div class="d-flex gap-1">
                    ${admin ? `<a href="#/units/${u.id}/edit" class="btn btn-xs btn-outline-secondary py-0 px-1" style="font-size:.7rem;" title="Edit unit"><i class="fas fa-edit"></i></a>` : ''}
                    <a href="#/staff?unit=${u.id}" class="btn btn-xs btn-outline-primary py-0 px-1" style="font-size:.7rem;" title="View staff"><i class="fas fa-users"></i></a>
                  </div>
                </div>`).join('')}
              </div>` : '<p class="text-muted mb-2" style="font-size:.82rem;"><i class="fas fa-info-circle me-1"></i>No units yet</p>'}
              <div class="d-flex gap-3 mt-2">
                <div class="text-center">
                  <div style="font-size:1.1rem;font-weight:700;color:#2E86C1;">${d.unit_count}</div>
                  <small class="text-muted">Units</small>
                </div>
              </div>
            </div>
            <div class="card-footer bg-transparent d-flex gap-2">
              <a href="#/units?dept=${d.id}" class="btn btn-outline-primary btn-sm flex-fill"><i class="fas fa-layer-group me-1"></i> Units</a>
              ${admin ? `<a href="#/units/new?dept=${d.id}" class="btn btn-outline-secondary btn-sm flex-fill"><i class="fas fa-plus me-1"></i> Add Unit</a>` : ''}
            </div>
          </div>
        </div>`).join('') || emptyState('hospital', 'No departments yet',
          `<a href="#/departments/new" class="btn btn-primary mt-2"><i class="fas fa-plus me-1"></i> Add First Department</a>`)}
      </div>
      ${pagerHtml(data, '/departments', { hospital: params.hospital })}`,
  });
}

/* ------------------------------------------------------------------ units */

async function viewUnits(m, params) {
  const [data, lk] = await Promise.all([Api.get('/api/units/', params), lookups()]);
  const admin = isAdmin();
  const depts = lk.departments.filter((d) => !params.hospital || String(d.hospital) === params.hospital);
  render({
    title: 'Units',
    actions: admin ? `<a href="#/units/new" class="btn btn-primary btn-sm"><i class="fas fa-plus me-1"></i> Add Unit</a>` : '',
    body: `
      ${filterBarHtml('Hospital:', '/units', params, 'hospital', [], lk.hospitals, (h) => trunc(h.name, 25))}
      ${filterBarHtml('Department:', '/units', params, 'dept', ['hospital'], depts, (d) => d.department_name, 'mb-4')}
      <div class="row g-3">
        ${data.results.map((u) => `
        <div class="col-md-6 col-lg-4">
          <div class="card h-100">
            <div class="card-body">
              <div class="d-flex align-items-start justify-content-between mb-3">
                <div class="d-flex align-items-center gap-2">
                  ${iconTile('layer-group', 40)}
                  <div>
                    <div style="font-weight:700;font-size:.9rem;color:#1B4F72;">${esc(trunc(u.unit_name, 40))}</div>
                    <small class="text-muted">${esc(u.department_name)}</small>
                    <br><small class="text-muted" style="font-size:.75rem;">${esc(trunc(u.hospital_name, 30))}</small>
                  </div>
                </div>
                ${admin ? dropdownHtml([
                  { href: `/units/${u.id}/edit`, icon: 'edit', text: 'Edit' },
                  { href: `/units/${u.id}/delete`, icon: 'trash', text: 'Delete', danger: true },
                ]) : ''}
              </div>
              <div class="d-flex gap-3">
                <div class="text-center">
                  <div style="font-size:1.3rem;font-weight:700;color:#1B4F72;">${u.staff_count}</div>
                  <small class="text-muted">Staff</small>
                </div>
                <div class="text-center">
                  <div style="font-size:1.3rem;font-weight:700;color:#7d3c98;">${u.roster_count}</div>
                  <small class="text-muted">Rosters</small>
                </div>
              </div>
            </div>
            <div class="card-footer bg-transparent d-flex gap-2">
              <a href="#/staff?unit=${u.id}" class="btn btn-outline-primary btn-sm flex-fill"><i class="fas fa-users me-1"></i> Staff</a>
              <a href="#/rosters/generate" class="btn btn-primary btn-sm flex-fill"><i class="fas fa-magic me-1"></i> Roster</a>
            </div>
          </div>
        </div>`).join('') || emptyState('layer-group', 'No units yet', `
          <p class="text-muted">Add units to departments first, then assign staff to units.</p>
          <a href="#/units/new" class="btn btn-primary mt-2"><i class="fas fa-plus me-1"></i> Add First Unit</a>`)}
      </div>
      ${pagerHtml(data, '/units', { hospital: params.hospital, dept: params.dept })}`,
  });
}

/* ------------------------------------------------------------------ staff */

async function viewStaff(m, params) {
  const [data, lk] = await Promise.all([Api.get('/api/staff/', params), lookups()]);
  const depts = lk.departments.filter((d) => !params.hospital || String(d.hospital) === params.hospital);
  const units = lk.units.filter((u) => (!params.hospital || String(u.hospital) === params.hospital)
    && (!params.dept || String(u.department) === params.dept));
  render({
    title: 'Staff Members',
    docTitle: 'Staff',
    actions: `<a href="#/staff/new" class="btn btn-primary btn-sm"><i class="fas fa-user-plus me-1"></i> Add Staff</a>`,
    body: `
      ${filterBarHtml('Hospital:', '/staff', params, 'hospital', [], lk.hospitals, (h) => trunc(h.name, 25))}
      ${filterBarHtml('Department:', '/staff', params, 'dept', ['hospital'], depts, (d) => d.department_name)}
      ${filterBarHtml('Unit:', '/staff', params, 'unit', ['hospital', 'dept'], units, (u) => trunc(u.unit_name, 30), 'mb-4')}
      <div class="card">
        <div class="card-body p-0">
          <table class="table table-modern mb-0">
            <thead><tr><th>Name</th><th>Phone</th><th>Hospital</th><th>Department</th><th>Unit</th><th>Status</th><th></th></tr></thead>
            <tbody>
              ${data.results.map((s) => `
              <tr>
                <td>
                  <div class="d-flex align-items-center gap-2">
                    <div style="width:34px;height:34px;background:${s.is_active ? '#d1fae5' : '#fee2e2'};border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:.75rem;color:${s.is_active ? '#065f46' : '#991b1b'};">
                      ${esc(s.name.slice(0, 2).toUpperCase())}
                    </div>
                    <div><div style="font-weight:600;font-size:.875rem;">${esc(s.display_name)}</div></div>
                  </div>
                </td>
                <td style="font-size:.82rem;color:#374151;">${esc(s.phone_number || '—')}</td>
                <td style="font-size:.82rem;color:#6b7280;">${esc(trunc(s.hospital_name, 30))}</td>
                <td style="font-size:.875rem;">${esc(s.department_name)}</td>
                <td style="font-size:.82rem;color:#374151;">${esc(trunc(s.unit_name, 30))}</td>
                <td>
                  <span class="badge ${s.is_active ? 'badge-active' : 'badge-inactive'}" style="font-size:.75rem;padding:4px 10px;border-radius:20px;">
                    ${s.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td class="text-end">
                  <a href="#/staff/${s.id}/availability" class="btn btn-sm btn-outline-warning me-1" title="Manage Unavailability"><i class="fas fa-calendar-times"></i></a>
                  <a href="#/staff/${s.id}/edit" class="btn btn-sm btn-outline-secondary me-1"><i class="fas fa-edit"></i></a>
                  <a href="#/staff/${s.id}/delete" class="btn btn-sm btn-outline-danger"><i class="fas fa-trash"></i></a>
                </td>
              </tr>`).join('') || `
              <tr>
                <td colspan="7" class="text-center py-5 text-muted">
                  <i class="fas fa-user-slash fa-3x mb-3 opacity-25 d-block"></i>
                  No staff found. <a href="#/staff/new">Add staff</a>.
                </td>
              </tr>`}
            </tbody>
          </table>
        </div>
      </div>
      ${pagerHtml(data, '/staff', { hospital: params.hospital, dept: params.dept, unit: params.unit })}`,
  });
}

async function viewStaffForm(id, params) {
  const [lk, s] = await Promise.all([lookups(), id ? Api.get(`/api/staff/${id}/`)
    : { unit: params.unit, staff_type: 'PHARM', title: 'PHARM.', is_active: true }]);
  const unit = lk.units.find((u) => String(u.id) === String(s.unit ?? ''));
  const selHospital = unit?.hospital ?? '';
  const selDept = unit?.department ?? '';
  const title = id ? 'Edit Staff' : 'Add Staff';
  const err = (name) => `<div class="text-danger small" data-err="${name}" hidden></div>`;
  const opt = (value, text, selected, extra = '') => `<option value="${value}" ${extra} ${selected ? 'selected' : ''}>${esc(text)}</option>`;

  render({
    title,
    body: `
      <div class="row justify-content-center">
        <div class="col-md-8">
          <div class="card">
            <div class="card-header" style="background:#1B4F72;color:#fff;">
              <i class="fas fa-user-md me-2"></i>${title}
            </div>
            <div class="card-body p-4">
              <form id="staffForm">
                <div class="alert alert-danger" data-err="__all__" hidden></div>
                <!-- Hospital → Department → Unit cascade (hospital/dept are JS-only filters) -->
                <div class="row g-3 mb-3">
                  <div class="col-md-4">
                    <label class="form-label">Hospital <small class="text-muted">(filter)</small></label>
                    <select id="hospital-filter" class="form-select">
                      <option value="">— All Hospitals —</option>
                      ${lk.hospitals.map((h) => opt(h.id, h.name, h.id === selHospital)).join('')}
                    </select>
                  </div>
                  <div class="col-md-4">
                    <label class="form-label">Department <small class="text-muted">(filter)</small></label>
                    <select id="dept-filter" class="form-select">
                      <option value="">— All Departments —</option>
                      ${lk.departments.map((d) => opt(d.id, d.department_name, d.id === selDept, `data-hospital="${d.hospital}"`)).join('')}
                    </select>
                  </div>
                  <div class="col-md-4">
                    <label class="form-label">Unit <span class="text-danger">*</span></label>
                    <select name="unit" class="form-select" required id="id_unit">
                      <option value="">---------</option>
                      ${lk.units.map((u) => opt(u.id, u.str, u.id === unit?.id)).join('')}
                    </select>
                    ${err('unit')}
                  </div>
                </div>

                <div class="row g-3 mb-3">
                  <div class="col-md-4">
                    <label class="form-label">Staff Type <span class="text-danger">*</span></label>
                    <select name="staff_type" class="form-select" id="id_staff_type">
                      ${opt('PHARM', 'Pharmacist', s.staff_type === 'PHARM')}
                      ${opt('PTECH', 'Pharmacy Technician', s.staff_type === 'PTECH')}
                    </select>
                    ${err('staff_type')}
                  </div>
                </div>

                <div class="row g-3 mb-3">
                  <div class="col-md-3">
                    <label class="form-label">Title</label>
                    <input type="text" name="title" class="form-control" placeholder="e.g. PHARM." maxlength="50" required id="id_title" value="${esc(s.title)}">
                    ${err('title')}
                  </div>
                  <div class="col-md-9">
                    <label class="form-label">Full Name <span class="text-danger">*</span></label>
                    <input type="text" name="name" class="form-control" placeholder="e.g. IBRAHIM ABUKUR" maxlength="200" required id="id_name" value="${esc(s.name)}">
                    ${err('name')}
                  </div>
                </div>

                <div class="row g-3 mb-3">
                  <div class="col-md-4">
                    <label class="form-label">Phone Number</label>
                    <input type="text" name="phone_number" class="form-control" placeholder="e.g. 08012345678" maxlength="20" id="id_phone_number" value="${esc(s.phone_number)}">
                    ${err('phone_number')}
                  </div>
                </div>

                <div class="mb-3 form-check">
                  <input type="checkbox" name="is_active" class="form-check-input" id="id_is_active" ${s.is_active ? 'checked' : ''}>
                  <label class="form-check-label" for="id_is_active">Active</label>
                </div>

                <button type="submit" class="btn btn-primary mt-2"><i class="fas fa-save me-1"></i> Save Staff</button>
              </form>
            </div>
          </div>
          <div class="mt-3">
            <a href="#/staff" class="text-muted text-decoration-none"><i class="fas fa-arrow-left me-1"></i> Back to Staff</a>
          </div>
        </div>
      </div>`,
  });

  const hospitalFilter = $('#hospital-filter');
  const deptFilter = $('#dept-filter');
  const unitSelect = $('#id_unit');

  function filterUnitsByDept(deptId) {
    const validIds = new Set(lk.units.filter((u) => String(u.department) === deptId).map((u) => String(u.id)));
    [...unitSelect.options].forEach((o) => { o.style.display = (!deptId || !o.value || validIds.has(o.value)) ? '' : 'none'; });
    if (!deptId) return;
    // Auto-select if only one unit
    const visible = [...unitSelect.options].filter((o) => o.value && o.style.display !== 'none');
    if (visible.length === 1 && !unitSelect.value) unitSelect.value = visible[0].value;
    // If current unit not in filtered set, clear it
    if (unitSelect.value && !validIds.has(unitSelect.value)) unitSelect.value = '';
  }

  function filterDeptsByHospital(hospitalId) {
    [...deptFilter.options].forEach((o) => {
      o.style.display = (!o.value || !hospitalId || o.dataset.hospital === hospitalId) ? '' : 'none';
    });
    // If current dept no longer visible, reset it
    const cur = deptFilter.selectedOptions[0];
    if (deptFilter.value && cur.style.display === 'none') {
      deptFilter.value = '';
      filterUnitsByDept('');
    }
  }

  hospitalFilter.addEventListener('change', () => filterDeptsByHospital(hospitalFilter.value));
  deptFilter.addEventListener('change', () => filterUnitsByDept(deptFilter.value));
  if (hospitalFilter.value) filterDeptsByHospital(hospitalFilter.value);
  if (deptFilter.value) filterUnitsByDept(deptFilter.value);

  // Auto-set title based on staff type
  const staffType = $('#id_staff_type');
  const titleInput = $('#id_title');
  const syncTitle = () => {
    if (staffType.value === 'PTECH' && titleInput.value === 'PHARM.') titleInput.value = 'PTECH.';
    else if (staffType.value === 'PHARM' && titleInput.value === 'PTECH.') titleInput.value = 'PHARM.';
  };
  staffType.addEventListener('change', syncTitle);
  syncTitle();

  const form = $('#staffForm');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const saved = await submitForm(form, id ? `/api/staff/${id}/` : '/api/staff/');
    if (!saved) return;
    flash(id ? 'Staff updated.' : `${saved.str} added.`);
    go('#/staff');
  });
}

async function viewAvailability(id) {
  const { staff, records } = await Api.get(`/api/staff/${id}/availability/`);
  const field = (name, label, type, extra = '') => `
    <div class="col-md-4">
      <div id="div_id_${name}" class="mb-3">
        <label for="id_${name}" class="form-label${extra.includes('required') ? ' requiredField' : ''}">${label}${extra.includes('required') ? '<span class="asteriskField">*</span>' : ''}</label>
        <input type="${type}" name="${name}" class="form-control" id="id_${name}" ${extra}>
        <span class="invalid-feedback" style="display:block" data-err="${name}" hidden></span>
      </div>
    </div>`;
  render({
    title: `Unavailability — ${staff.display_name}`,
    docTitle: `Availability — ${staff.display_name}`,
    actions: `<a href="#/staff" class="btn btn-outline-secondary btn-sm"><i class="fas fa-arrow-left me-1"></i> Back to Staff</a>`,
    body: `
      <div class="row g-4">
        <div class="col-lg-5">
          <div class="card">
            <div class="card-header" style="background:#1B4F72;color:#fff;font-weight:600;font-size:.9rem;">
              <i class="fas fa-calendar-times me-2"></i> Mark Unavailable Period
            </div>
            <div class="card-body">
              <p class="text-muted mb-3" style="font-size:.83rem;">
                Dates added here will be skipped when generating rosters — the next available staff will cover those days.
              </p>
              <form id="availForm">
                <div class="alert alert-block alert-danger" data-err="__all__" hidden></div>
                <div class="row">
                  ${field('start_date', 'Start date', 'date', 'required')}
                  ${field('end_date', 'End date', 'date', 'required')}
                  ${field('reason', 'Reason', 'text', 'maxlength="200" placeholder="e.g. Annual leave, Training"')}
                </div>
                <input type="submit" name="submit" value="Save" class="btn btn-primary mt-2">
              </form>
            </div>
          </div>
        </div>

        <div class="col-lg-7">
          <div class="card">
            <div class="card-header" style="background:#154360;color:#fff;font-weight:600;font-size:.9rem;">
              <i class="fas fa-list me-2"></i> Recorded Unavailability Periods
            </div>
            <div class="card-body p-0">
              <table class="table table-modern mb-0">
                <thead><tr><th>From</th><th>To</th><th>Reason</th><th></th></tr></thead>
                <tbody>
                  ${records.map((r) => `
                  <tr>
                    <td style="font-size:.875rem;font-weight:600;">${esc(r.start)}</td>
                    <td style="font-size:.875rem;">${esc(r.end)}</td>
                    <td style="font-size:.82rem;color:#6b7280;">${esc(r.reason || '—')}</td>
                    <td class="text-end">
                      <button type="button" class="btn btn-sm btn-outline-danger" data-remove="${r.id}"><i class="fas fa-trash"></i></button>
                    </td>
                  </tr>`).join('') || `
                  <tr>
                    <td colspan="4" class="text-center py-5 text-muted">
                      <i class="fas fa-calendar-check fa-3x mb-3 opacity-25 d-block"></i>
                      No unavailability periods recorded. ${esc(staff.display_name)} is available all days.
                    </td>
                  </tr>`}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>`,
  });

  const form = $('#availForm');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!await submitForm(form, `/api/staff/${id}/availability/`)) return;
    flash('Unavailability period saved.');
    route();
  });
  $$('[data-remove]').forEach((btn) => btn.addEventListener('click', async () => {
    if (!confirm('Remove this unavailability record?')) return;
    await Api.del(`/api/availability/${btn.dataset.remove}/`);
    flash('Unavailability record removed.');
    route();
  }));
}

/* ---------------------------------------------------------------- rosters */

const exportUrl = (id) => `/api/rosters/${id}/export/`;

async function viewRosters(m, params) {
  const data = await Api.get('/api/rosters/', { page: params.page });
  const pill = (bg, fg, text) => `<span class="badge" style="background:${bg};color:${fg};font-size:.75rem;padding:3px 8px;border-radius:12px;">${text}</span>`;
  render({
    title: 'All Rosters',
    docTitle: 'Rosters',
    actions: `<a href="#/rosters/generate" class="btn btn-primary btn-sm"><i class="fas fa-magic me-1"></i> Generate Roster</a>`,
    body: `
      <div class="card">
        <div class="card-body p-0">
          <table class="table table-modern mb-0">
            <thead><tr><th>Title</th><th>Unit</th><th>Period</th><th>Type</th><th>Entries</th><th>Created</th><th></th></tr></thead>
            <tbody>
              ${data.results.map((r) => `
              <tr>
                <td style="font-weight:600;font-size:.875rem;">${esc(r.roster_title)}</td>
                <td style="font-size:.82rem;">${esc(trunc(r.unit_name, 35))}</td>
                <td>
                  <span class="badge" style="background:#e8f0f7;color:#1B4F72;font-weight:600;font-size:.8rem;padding:5px 10px;border-radius:20px;">${esc(r.period)}</span>
                </td>
                <td style="font-size:.82rem;">
                  ${r.roster_type === 'PTECH' ? pill('#fef3c7', '#92400e', 'PTech') : pill('#e8f0f7', '#1B4F72', `Call (${r.num_slots}s)`)}
                </td>
                <td style="font-size:.875rem;">${r.entries_count}</td>
                <td style="font-size:.82rem;color:#6b7280;">${esc(r.created)}</td>
                <td class="text-end">
                  <div class="d-flex gap-1 justify-content-end">
                    <a href="#/rosters/${r.id}" class="btn btn-sm btn-outline-primary" title="View"><i class="fas fa-eye"></i></a>
                    <a href="${exportUrl(r.id)}" class="btn btn-sm btn-success" title="Export Excel"><i class="fas fa-file-excel"></i></a>
                    <a href="#/rosters/${r.id}/delete" class="btn btn-sm btn-outline-danger" title="Delete"><i class="fas fa-trash"></i></a>
                  </div>
                </td>
              </tr>`).join('') || `
              <tr>
                <td colspan="7" class="text-center py-5 text-muted">
                  <i class="fas fa-calendar-times fa-3x mb-3 opacity-25 d-block"></i>
                  No rosters yet. <a href="#/rosters/generate">Generate one</a>.
                </td>
              </tr>`}
            </tbody>
          </table>
        </div>
      </div>
      ${pagerHtml(data, '/rosters', {})}`,
  });
}

const SHIFTS = [['M', 'Morning'], ['A', 'Afternoon'], ['N', 'Night'], ['CM', 'Combined Morning'], ['O', 'Off'], ['L', 'Leave']];

async function viewRoster(id) {
  const r = await Api.get(`/api/rosters/${id}/`);
  const badge = (bg, fg, html, extra = 'font-size:.8rem;padding:5px 12px;') =>
    `<span class="badge ms-2" style="background:${bg};color:${fg};${extra}border-radius:20px;">${html}</span>`;
  const typeBadges = r.roster_type === 'PTECH'
    ? badge('#fef3c7', '#92400e', '<i class="fas fa-clock me-1"></i>PTech Shift Roster')
      + (r.shift_config_display ? badge('#e0e7ff', '#3730a3', esc(r.shift_config_display)) : '')
    : r.roster_type === 'PHARM_SHIFT'
      ? badge('#d1fae5', '#065f46', '<i class="fas fa-clock me-1"></i>Pharmacist Shift Roster')
      : badge('#e8f0f7', '#1B4F72', '<i class="fas fa-phone me-1"></i>Call Duty Roster');
  const slots = r.slot_labels.slice(0, r.num_slots);
  const empty = '<span class="empty-cell">—</span>';
  const staffOptions = r.all_staff.map((s) => `<option value="${s.id}">${esc(s.display_name)}</option>`).join('');
  const modalHead = (tag, text) => `
    <div class="modal-header" style="background:#1B4F72;color:#fff;border-radius:12px 12px 0 0;">
      <${tag} class="modal-title"><i class="fas fa-pencil-alt me-2"></i>${text}</${tag}>
      <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
    </div>`;

  const matrix = () => `
    <div class="card">
      <div class="card-header d-flex align-items-center justify-content-between" style="background:#fff;border-bottom:2px solid #e8f0f7;">
        <span style="font-weight:600;color:#1B4F72;"><i class="fas fa-table me-2"></i>Shift Matrix</span>
        <small class="text-muted"><i class="fas fa-info-circle me-1"></i>Click any shift cell to edit</small>
      </div>
      <div class="card-body">
        <div class="shift-legend">${SHIFTS.map(([c, n]) => `<span class="shift-${c}">${c} — ${n}</span>`).join('')}</div>
        <div class="table-responsive">
          <table class="ptech-matrix">
            <thead>
              <tr>
                <th class="staff-name">Staff</th>
                ${r.dates.map((d) => `<th class="${d.weekend ? 'wknd-th' : 'day-th'}">${d.day}</th>`).join('')}
              </tr>
              <tr>
                <th class="staff-name" style="font-size:.7rem;font-weight:400;color:#bbb;background:#1B4F72;">—</th>
                ${r.dates.map((d) => `<th class="${d.weekend ? 'wknd-th' : 'day-th'}" style="font-size:.68rem;">${d.dow}</th>`).join('')}
              </tr>
            </thead>
            <tbody>
              ${r.rows.map((row) => `
              <tr>
                <td class="staff-name">${esc(row.staff)}</td>
                ${row.cells.map((c, i) => {
                  const shift = c?.shift || 'O';
                  return `<td class="shift-cell shift-${shift}" data-entry-id="${c?.id ?? ''}" data-current="${shift}" title="${esc(r.dates[i].title)} — ${shift}">${shift}</td>`;
                }).join('')}
              </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>
    </div>
    <div class="modal fade" id="ptechEditModal" tabindex="-1">
      <div class="modal-dialog modal-dialog-centered modal-sm">
        <div class="modal-content" style="border-radius:12px;">
          ${modalHead('h6', 'Edit Shift')}
          <div class="modal-body p-3">
            <select class="form-select" id="ptech_shift_select">
              ${SHIFTS.map(([c, n]) => `<option value="${c}">${c} — ${n}</option>`).join('')}
            </select>
          </div>
          <div class="modal-footer py-2">
            <button type="button" class="btn btn-outline-secondary btn-sm" data-bs-dismiss="modal">Cancel</button>
            <button type="button" class="btn btn-primary btn-sm" id="ptechSaveBtn">Save</button>
          </div>
        </div>
      </div>
    </div>`;

  const callTable = () => `
    <div class="card">
      <div class="card-header d-flex align-items-center justify-content-between" style="background:#fff;border-bottom:2px solid #e8f0f7;">
        <span style="font-weight:600;color:#1B4F72;"><i class="fas fa-table me-2"></i>Roster Entries</span>
        <small class="text-muted"><i class="fas fa-info-circle me-1"></i>Click <i class="fas fa-pencil-alt"></i> on any row to edit</small>
      </div>
      <div class="card-body p-0">
        <div class="table-responsive">
          <table class="roster-view-table">
            <thead>
              <tr>
                <th style="width:60px;">Day</th>
                <th style="width:110px;">Date</th>
                ${slots.map((l) => `<th>${esc(l)}</th>`).join('')}
                <th style="width:50px;"></th>
              </tr>
            </thead>
            <tbody>
              ${r.entries.map((e) => `
              <tr class="${e.weekend ? 'weekend' : ''}">
                <td><span class="day-badge ${e.weekend ? 'day-weekend' : 'day-weekday'}">${e.day_abbr}</span></td>
                <td style="font-weight:500;color:#374151;">${e.date_display}</td>
                ${slots.map((_, i) => `<td class="staff-cell" id="s${i + 1}-${e.id}">${e.slots[i] ? esc(e.slots[i].name) : empty}</td>`).join('')}
                <td>
                  <button class="btn btn-sm btn-light edit-btn" data-edit="${e.id}" title="Edit">
                    <i class="fas fa-pencil-alt" style="font-size:.75rem;"></i>
                  </button>
                </td>
              </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>
    </div>
    <div class="modal fade" id="editModal" tabindex="-1">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content" style="border-radius:12px;">
          ${modalHead('h5', 'Edit Entry')}
          <div class="modal-body p-4">
            ${slots.map((l, i) => `
            <div class="mb-3">
              <label class="form-label">${esc(l)}</label>
              <select class="form-select" id="edit_slot${i + 1}">
                <option value="">— None —</option>
                ${staffOptions}
              </select>
            </div>`).join('')}
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Cancel</button>
            <button type="button" class="btn btn-primary" id="saveEditBtn"><i class="fas fa-save me-1"></i>Save Changes</button>
          </div>
        </div>
      </div>
    </div>`;

  render({
    title: `${r.month_display} ${r.year} Roster`,
    docTitle: r.str,
    actions: `
      <a href="${exportUrl(r.id)}" class="btn btn-success btn-sm"><i class="fas fa-file-excel me-1"></i> Export Excel</a>
      <a href="#/rosters/${r.id}/delete" class="btn btn-outline-danger btn-sm"><i class="fas fa-trash me-1"></i> Delete</a>`,
    body: `
      <div class="card mb-4" style="border-top: 4px solid #1B4F72;">
        <div class="card-body">
          <div class="row align-items-center">
            <div class="col-md-8">
              <div style="font-size:.78rem;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px;">${esc(r.hospital_name)}</div>
              <h4 style="font-weight:700;color:#1B4F72;margin-bottom:4px;">${esc(r.roster_title)}</h4>
              <div style="font-size:.9rem;color:#374151;">${esc(r.department_name)} &mdash; ${esc(r.unit_name)}</div>
              <div class="mt-2">
                <span class="badge" style="background:#e8f0f7;color:#1B4F72;font-size:.85rem;padding:6px 14px;border-radius:20px;">
                  <i class="fas fa-calendar me-1"></i>${esc(r.month_year_display)}
                </span>
                ${badge('#f0fdf4', '#065f46', `${r.is_ptech ? r.dates.length : r.entries.length} days`)}
                ${typeBadges}
              </div>
            </div>
            <div class="col-md-4 text-md-end mt-3 mt-md-0">
              <a href="${exportUrl(r.id)}" class="btn btn-success"><i class="fas fa-file-excel me-2"></i>Download Excel</a>
            </div>
          </div>
        </div>
      </div>

      ${r.is_ptech ? matrix() : callTable()}

      <div class="card mt-4">
        <div class="card-header" style="background:#fff;border-bottom:2px solid #e8f0f7;">
          <span style="font-weight:600;color:#1B4F72;"><i class="fas fa-address-book me-2"></i>Staff Contacts</span>
        </div>
        <div class="card-body p-0">
          <div class="table-responsive">
            <table class="roster-view-table">
              <thead><tr><th style="text-align:left;">Staff</th><th style="width:200px;">Phone</th></tr></thead>
              <tbody>
                ${r.all_staff.map((s) => `
                <tr>
                  <td class="staff-cell" style="text-align:left;">${esc(s.display_name)}</td>
                  <td>${s.phone_number ? `<a href="tel:${esc(s.phone_number)}">${esc(s.phone_number)}</a>` : empty}</td>
                </tr>`).join('') || '<tr><td colspan="2" class="empty-cell">No staff assigned to this unit.</td></tr>'}
              </tbody>
            </table>
          </div>
        </div>
      </div>`,
  });

  if (r.is_ptech) {
    const modal = new bootstrap.Modal($('#ptechEditModal'));
    let cell = null;
    $('.ptech-matrix').addEventListener('click', (e) => {
      const td = e.target.closest('.shift-cell');
      if (!td || !td.dataset.entryId) return;
      cell = td;
      $('#ptech_shift_select').value = td.dataset.current || 'O';
      modal.show();
    });
    $('#ptechSaveBtn').addEventListener('click', async () => {
      if (!cell) return;
      const data = await Api.post(`/api/ptech-entries/${cell.dataset.entryId}/`, { shift: $('#ptech_shift_select').value });
      cell.textContent = data.shift;
      cell.className = `shift-cell shift-${data.shift}`;
      cell.dataset.current = data.shift;
      modal.hide();
    });
    return;
  }

  const modal = new bootstrap.Modal($('#editModal'));
  const entries = new Map(r.entries.map((e) => [String(e.id), e]));
  let current = null;
  $('.roster-view-table').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-edit]');
    if (!btn) return;
    current = entries.get(btn.dataset.edit);
    slots.forEach((_, i) => { $(`#edit_slot${i + 1}`).value = current.slots[i]?.id ?? ''; });
    modal.show();
  });
  $('#saveEditBtn').addEventListener('click', async () => {
    const body = Object.fromEntries(slots.map((_, i) => [`slot${i + 1}`, $(`#edit_slot${i + 1}`).value]));
    const data = await Api.post(`/api/entries/${current.id}/`, body);
    slots.forEach((_, i) => {
      const n = i + 1;
      $(`#s${n}-${current.id}`).innerHTML = data[`slot${n}`] ? esc(data[`slot${n}`]) : empty;
      const id = body[`slot${n}`];
      current.slots[i] = id ? { id: Number(id), name: data[`slot${n}`] } : null;
    });
    modal.hide();
  });
}

/* ------------------------------------------------------- generate roster */

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const DAYS_PATTERNS = [['all', 'Every day'], ['weekdays', 'Weekdays only (Mon–Fri)'], ['weekends', 'Weekends only (Sat–Sun)'], ['custom', 'Custom days']];
const MODES = [['rotate', 'Rotate (round-robin)'], ['fixed', 'Fixed (always first selected)']];
const TITLES = {
  CALL: "PHARMACISTS' CALL DUTY ROSTER",
  PTECH: "PHARMACY TECHNICIAN'S DUTY ROSTER",
  PHARM_SHIFT: "PHARMACISTS' SHIFT DUTY ROSTER",
};

/* Checkbox + label pairs laid out as form-check rows. */
function checksHtml(name, choices, { type = 'checkbox', checked = [], inline = true, labelClass = '', extra = '' } = {}) {
  return choices.map(([value, text], i) => `
    <div class="form-check${inline ? ' form-check-inline' : ''}">
      <input type="${type}" name="${name}" value="${value}" id="id_${name}_${i}" class="form-check-input" ${extra} ${checked.includes(value) ? 'checked' : ''}>
      <label class="form-check-label${labelClass}" for="id_${name}_${i}">${text}</label>
    </div>`).join('');
}

/* A pool of staff checkboxes; each row can carry a start date (and, for slot
 * 1, an appearance cap) named `<prefix>_start_<id>` / `slot1_count_<id>`. */
function staffGridHtml(gridId, field, prefix, staff, { cap = false, small = false } = {}) {
  return `
    <div class="staff-checkbox-grid${small ? ' ptech-staff-grid' : ''}" id="${gridId}">
      ${staff.map((s, i) => `
      <label data-staff-id="${s.id}">
        <input type="checkbox" name="${field}" value="${s.id}" id="id_${field}_${i}"><span>${esc(s.str)}</span>
        ${cap ? `<input type="number" min="1" name="slot1_count_${s.id}" class="slot1-count-input" placeholder="∞"
                   title="Max times in first-on-call (blank = unlimited)"
                   style="width:50px; margin-left:auto; font-size:.78rem; padding:1px 4px;">` : ''}
        <input type="date" name="${prefix}_start_${s.id}" title="Include from this date (blank = whole month)"
               style="width:130px;${cap ? '' : ' margin-left:auto;'} font-size:${small ? '.7rem' : '.72rem'}; padding:1px ${small ? 3 : 4}px;">
      </label>`).join('')}
    </div>
    <div class="text-danger small mt-1" data-err="${field}" hidden></div>`;
}

const numInput = (name, value, min, max, width = 70) =>
  `<input type="number" name="${name}" value="${value}" min="${min}" max="${max}" class="form-control form-control-sm" style="width:${width}px" id="id_${name}">`;

function slotCardHtml(n, staff) {
  const color = ['#1B4F72', '#2E86C1', '#7d3c98'][n - 1];
  const label = ['FIRST ON CALL', 'SECOND ON CALL', 'THIRD ON CALL'][n - 1];
  return `
    <div class="section-card${n > 1 ? ` slot-section slot${n}-section` : ''}" id="slot${n}-card">
      <h6><i class="fas fa-user-circle me-2" style="color:${color};"></i>Slot ${n} — <span id="slot${n}_label_display">${label}</span></h6>
      <div class="mb-3">
        ${n === 1 ? `
        <label class="form-label">Staff Pool <small class="text-muted">(select staff to include in this slot)</small></label>
        <p class="staff-hint">Select a unit above to highlight that unit's staff.</p>
        <p class="staff-hint">Set a number to cap how many times that staff appears in this slot; leave blank for unlimited.</p>
        <p class="staff-hint">Set a date to include a staff only from that day onward (e.g. joined mid-month); leave blank for the whole month.</p>`
        : '<label class="form-label">Staff Pool</label>'}
        ${staffGridHtml(`slot${n}-staff-grid`, `slot${n}_staff`, `slot${n}`, staff, { cap: n === 1 })}
      </div>
      <div class="mode-radio">
        <label class="form-label">Assignment Mode</label>
        <div class="d-flex gap-4">${checksHtml(`slot${n}_mode`, MODES, { type: 'radio', inline: false, checked: [n === 1 ? 'rotate' : 'fixed'] })}</div>
      </div>
      <div class="pattern-section">
        <div class="section-label"><i class="fas fa-calendar-alt me-1"></i>Pattern Instructions</div>
        <div class="days-inline" id="slot${n}-days-pattern">
          ${checksHtml(`slot${n}_days_pattern`, DAYS_PATTERNS, { type: 'radio', checked: ['all'] })}
        </div>
        <div class="custom-days-row" id="slot${n}-custom-days-row">
          ${checksHtml(`slot${n}_custom_days`, DAYS.map((d, i) => [String(i), d]))}
        </div>
        <div class="min-gap-row">
          <label for="id_slot${n}_min_gap">Min days between same staff (0 = no restriction):</label>
          ${numInput(`slot${n}_min_gap`, 0, 0, 6, 80)}
        </div>
      </div>
    </div>`;
}

/* The pharmacist- and PTech-shift sections share a layout; `p` is the field
 * prefix, `nightField` the night pool's field name (PTech's is ptech_cm_staff). */
function shiftSectionHtml(p, staff, { title, icon, note, nightField, nightGrid }) {
  const col = (shift, key, label, icon2, field, gridId, work, off) => `
    <div class="col-md-4" id="${p}-${key}-col">
      <label class="form-label fw-semibold" style="color:${{ M: '#1A5276', A: '#1E8449', N: '#6C3483' }[shift]};">
        <span class="shift-badge shift-${shift}-badge">${shift}</span> ${label} Staff
      </label>
      <div class="d-flex gap-2 align-items-center mb-2" style="font-size:.82rem; color:#4b5563;">
        <i class="fas fa-${icon2} me-1"></i>
        <label for="id_${p}_${key}_work_days" class="mb-0">Work:</label>
        ${numInput(`${p}_${key}_work_days`, work, 1, 30)}
        <span>days &nbsp; Off:</span>
        ${numInput(`${p}_${key}_off_days`, off, 0, 30)}
        <span>days</span>
      </div>
      ${staffGridHtml(gridId, field, field.replace(/_staff$/, ''), staff, { small: true })}
      <div class="text-danger small mt-1" data-err="${p}_${key}_work_days" hidden></div>
    </div>`;
  return `
    <div class="section-card" id="${p}-section" style="display:none;">
      <div class="d-flex align-items-center justify-content-between mb-3">
        <h6 class="mb-0"><i class="fas fa-clock me-2" style="color:${icon};"></i>${title}</h6>
        <div class="form-check form-switch d-flex align-items-center gap-2 mb-0">
          <input type="checkbox" name="${p}_rotate_shifts" class="form-check-input" id="id_${p}_rotate_shifts" checked>
          <label class="form-check-label fw-semibold" for="id_${p}_rotate_shifts" style="font-size:.88rem;">Rotate Shifts</label>
        </div>
      </div>
      <div id="${p}-rotate-note" class="alert alert-info py-1 px-2 mb-3" style="font-size:.82rem; display:none;">
        <i class="fas fa-sync-alt me-1"></i>
        <strong>Rotation mode:</strong> All selected staff cycle through M&rarr;A&rarr;N shifts automatically.
        Staff are staggered evenly so every shift has coverage at all times.${note}
      </div>
      <div class="mb-3 pb-3 border-bottom">
        <label class="form-label fw-semibold">Shifts to include in this roster</label>
        <div class="d-flex gap-4 flex-wrap">
          ${checksHtml(`${p}_active_shifts`, [['M', 'Morning (M)'], ['A', 'Afternoon (A)'], ['N', 'Night (N)']], { checked: ['M', 'A', 'N'], labelClass: ' fw-semibold' })}
        </div>
        <div class="text-danger small mt-1" data-err="${p}_active_shifts" hidden></div>
      </div>
      <div class="row g-3">
        ${col('M', 'morning', 'Morning', 'sun', `${p}_morning_staff`, `${p}-morning-grid`, 5, 2)}
        ${col('A', 'afternoon', 'Afternoon', 'cloud-sun', `${p}_afternoon_staff`, `${p}-afternoon-grid`, 5, 2)}
        ${col('N', 'night', 'Night', 'moon', nightField, nightGrid, 2, 5)}
      </div>
      ${p === 'pharm' ? `
      <div class="mt-3 pt-2 border-top">
        <div class="min-gap-row">
          <label for="id_pharm_night_min_gap">Min days between Night assignments for same staff (0 = no restriction):</label>
          ${numInput('pharm_night_min_gap', 0, 0, 30, 80)}
        </div>
      </div>` : ''}
    </div>`;
}

async function viewGenerate() {
  const o = await Api.get('/api/rosters/generate/');
  render({
    title: 'Generate Roster',
    body: `
      <div class="row justify-content-center">
        <div class="col-xl-11">
          <form id="generateForm">
            <div class="alert alert-danger" data-err="__all__" hidden></div>

            <div class="section-card">
              <h6><i class="fas fa-info-circle me-2"></i><span id="roster-details-heading">Roster Details</span></h6>
              <div class="row g-3">
                <div class="col-md-6">
                  <label class="form-label">Department <small class="text-muted">(filter units)</small></label>
                  <select id="dept-filter" class="form-select">
                    <option value="">— All Departments —</option>
                    ${o.departments.map((d) => `<option value="${d.id}">${esc(d.label)}</option>`).join('')}
                  </select>
                </div>
                <div class="col-md-6">
                  <label class="form-label">Unit <span class="text-danger">*</span></label>
                  <select name="unit" class="form-select" id="id_unit" required>
                    <option value="">---------</option>
                    ${o.units.map((u) => `<option value="${u.id}">${esc(u.str)}</option>`).join('')}
                  </select>
                  <div class="text-danger small" data-err="unit" hidden></div>
                  <div class="unit-filter-note mt-1" id="unit-staff-note">
                    <i class="fas fa-filter me-1"></i>Staff checkboxes below filtered to this unit.
                    <a href="#" id="show-all-staff" class="ms-1">Show all</a>
                  </div>
                </div>
                <div class="col-md-6">
                  <label class="form-label">Roster Title</label>
                  <input type="text" name="roster_title" value="${esc(TITLES.CALL)}" class="form-control" required id="id_roster_title">
                  <div class="text-danger small" data-err="roster_title" hidden></div>
                </div>
                <div class="col-md-6">
                  <label class="form-label">Roster Type</label>
                  <div id="id_roster_type">
                    ${[['CALL', 'Call Duty Roster'], ['PTECH', 'PTech Shift Roster'], ['PHARM_SHIFT', 'Pharmacist Shift Roster']].map(([v, t], i) => `
                    <div><label for="id_roster_type_${i}"><input type="radio" name="roster_type" value="${v}" id="id_roster_type_${i}" required ${v === 'CALL' ? 'checked' : ''}> ${t}</label></div>`).join('')}
                  </div>
                  <div class="text-danger small" data-err="roster_type" hidden></div>
                </div>
                <div class="col-md-2">
                  <label class="form-label">Month</label>
                  <select name="month" class="form-select" id="id_month">
                    ${MONTHS.map((mo, i) => `<option value="${i + 1}">${String(i + 1).padStart(2, '0')} — ${mo}</option>`).join('')}
                  </select>
                </div>
                <div class="col-md-2">
                  <label class="form-label">Year</label>
                  <input type="number" name="year" value="${o.current_year}" class="form-control" min="2020" max="2100" required id="id_year">
                </div>
                <div class="col-md-2" id="num-slots-wrapper">
                  <label class="form-label">Slots</label>
                  <select name="num_slots" class="form-select" id="id_num_slots">
                    <option value="1">1 Slot</option><option value="2">2 Slots</option><option value="3" selected>3 Slots</option>
                  </select>
                </div>
              </div>
            </div>

            <div class="section-card" id="slot-labels-section">
              <h6><i class="fas fa-tag me-2"></i>Slot Labels</h6>
              <div class="row g-3">
                ${['FIRST ON CALL', 'SECOND ON CALL', 'THIRD ON CALL'].map((l, i) => `
                <div class="col-md-4${i ? ` slot-section slot${i + 1}-section` : ''}">
                  <label class="form-label">Slot ${i + 1} Label</label>
                  <input type="text" name="slot${i + 1}_label" value="${l}" class="form-control" id="id_slot${i + 1}_label" ${i ? '' : 'required'}>
                </div>`).join('')}
              </div>
            </div>

            ${[1, 2, 3].map((n) => slotCardHtml(n, o.pharm)).join('')}

            ${shiftSectionHtml('pharm', o.pharm, {
              title: 'Pharmacist Shift Configuration', icon: '#065f46', note: '',
              nightField: 'pharm_night_staff', nightGrid: 'pharm-night-grid' })}

            ${shiftSectionHtml('ptech', o.ptech, {
              title: 'PTech Shift Configuration', icon: '#D4AC0D',
              note: '\n        Use the pool checkboxes below to pick <em>which</em> staff participate; their pool label only sets the starting phase.',
              nightField: 'ptech_cm_staff', nightGrid: 'ptech-cm-grid' })}

            <div class="d-flex gap-3">
              <button type="submit" class="btn btn-primary px-5"><i class="fas fa-magic me-2"></i>Generate Roster</button>
              <a href="#/rosters" class="btn btn-outline-secondary">Cancel</a>
            </div>
          </form>
        </div>
      </div>`,
  });
  wireGenerate($('#generateForm'), o);
}

function wireGenerate(form, o) {
  const numSlots = $('#id_num_slots');
  const unitSelect = $('#id_unit');
  const deptFilter = $('#dept-filter');
  const unitNote = $('#unit-staff-note');
  const labelInputs = [1, 2, 3].map((n) => $(`#id_slot${n}_label`));
  const staffUnit = new Map([...o.pharm, ...o.ptech].map((s) => [String(s.id), String(s.unit)]));

  function updateLabels() {
    ['FIRST ON CALL', 'SECOND ON CALL', 'THIRD ON CALL'].forEach((fallback, i) => {
      $(`#slot${i + 1}_label_display`).textContent = labelInputs[i].value || fallback;
    });
  }

  function updateRosterType() {
    const type = form.elements.roster_type.value;
    const isPTech = type === 'PTECH';
    const isPharmShift = type === 'PHARM_SHIFT';
    const isShift = isPTech || isPharmShift;

    const titleText = isShift ? TITLES[type] : 'Generate Roster';
    $('#page-title').textContent = titleText;
    document.title = titleText;
    const title = form.elements.roster_title;
    if (title.value.trim() !== TITLES[type]) title.value = TITLES[type];
    $('#roster-details-heading').textContent = isShift ? TITLES[type] : 'Roster Details';

    $('#ptech-section').style.display = isPTech ? '' : 'none';
    $('#pharm-section').style.display = isPharmShift ? '' : 'none';
    $('#num-slots-wrapper').style.display = isShift ? 'none' : '';
    $('#slot-labels-section').style.display = isShift ? 'none' : '';
    [1, 2, 3].forEach((n) => { $(`#slot${n}-card`).style.display = isShift ? 'none' : ''; });
    if (!isShift) updateLabels();
  }

  function updateSlotVisibility() {
    const n = parseInt(numSlots.value, 10);
    $$('.slot2-section', form).forEach((el) => el.classList.toggle('visible', n >= 2));
    $$('.slot3-section', form).forEach((el) => el.classList.toggle('visible', n >= 3));
  }

  // Every pool shows only the chosen unit's active staff.
  function filterStaffByUnit(unitId) {
    $$('.staff-checkbox-grid label', form).forEach((label) => {
      label.style.display = staffUnit.get(label.dataset.staffId) === unitId ? '' : 'none';
    });
    unitNote.classList.add('visible');
  }
  function showAllStaff() {
    $$('.staff-checkbox-grid label', form).forEach((label) => { label.style.display = ''; });
    unitNote.classList.remove('visible');
  }

  deptFilter.addEventListener('change', () => {
    const deptId = deptFilter.value;
    const validIds = new Set(o.units.filter((u) => String(u.department) === deptId).map((u) => String(u.id)));
    [...unitSelect.options].forEach((opt) => {
      opt.style.display = (!deptId || !opt.value || validIds.has(opt.value)) ? '' : 'none';
    });
    if (!deptId) return;
    // Auto-select if only one unit in dept
    const visible = [...unitSelect.options].filter((opt) => opt.value && opt.style.display !== 'none');
    if (visible.length === 1) {
      unitSelect.value = visible[0].value;
      filterStaffByUnit(visible[0].value);
    }
  });
  unitSelect.addEventListener('change', () => (unitSelect.value ? filterStaffByUnit(unitSelect.value) : showAllStaff()));
  $('#show-all-staff').addEventListener('click', (e) => { e.preventDefault(); showAllStaff(); });

  $$('[name="roster_type"]', form).forEach((r) => r.addEventListener('change', updateRosterType));
  numSlots.addEventListener('change', updateSlotVisibility);
  labelInputs.forEach((el) => el.addEventListener('input', updateLabels));

  // Rotate-shifts toggles show the rotation note.
  ['ptech', 'pharm'].forEach((p) => {
    const toggle = form.elements[`${p}_rotate_shifts`];
    const note = $(`#${p}-rotate-note`);
    const update = () => { note.style.display = toggle.checked ? '' : 'none'; };
    toggle.addEventListener('change', update);
    update();
  });

  // Custom-days checkboxes only for the "Custom days" pattern.
  [1, 2, 3].forEach((n) => {
    const row = $(`#slot${n}-custom-days-row`);
    const update = () => row.classList.toggle('visible', form.elements[`slot${n}_days_pattern`].value === 'custom');
    $$(`[name="slot${n}_days_pattern"]`, form).forEach((r) => r.addEventListener('change', update));
    update();
  });

  // Unticked shifts hide their staff pool.
  ['ptech', 'pharm'].forEach((p) => {
    const cols = { M: `${p}-morning-col`, A: `${p}-afternoon-col`, N: `${p}-night-col` };
    const update = () => $$(`[name="${p}_active_shifts"]`, form).forEach((cb) => {
      $(`#${cols[cb.value]}`).style.display = cb.checked ? '' : 'none';
    });
    $$(`[name="${p}_active_shifts"]`, form).forEach((cb) => cb.addEventListener('change', update));
    update();
  });

  updateRosterType();
  updateSlotVisibility();
  updateLabels();

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const res = await submitForm(form, '/api/rosters/generate/');
    if (!res) return;
    flash(res.message);
    go(`#/rosters/${res.id}`);
  });
}

/* ----------------------------------------------------------- activity log */

async function viewActivity(m, params) {
  const data = await Api.get('/api/activity/', params);
  const th = (t) => `<th style="font-size:.75rem;color:#6b7280;font-weight:600;padding:10px 16px;">${t}</th>`;
  const sel = (value, current) => (value === (current || '') ? 'selected' : '');
  const filters = { action: params.action, object_type: params.object_type };
  render({
    title: 'Activity Log',
    body: `
      <div class="card">
        <div class="card-header d-flex align-items-center justify-content-between" style="background:#fff; border-bottom:2px solid #e8f0f7;">
          <span style="color:#1B4F72;"><i class="fas fa-history me-2"></i>User Activity Log</span>
          <span class="text-muted" style="font-size:.8rem;">${data.count} total entries</span>
        </div>
        <div class="card-body border-bottom py-2">
          <form id="logFilter" class="d-flex gap-2 flex-wrap align-items-center">
            <select name="action" class="form-select form-select-sm" style="width:auto;">
              <option value="">All Actions</option>
              ${Object.entries(ACTION_BADGES).map(([v, b]) => `<option value="${v}" ${sel(v, params.action)}>${b[2]}</option>`).join('')}
            </select>
            <select name="object_type" class="form-select form-select-sm" style="width:auto;">
              <option value="">All Types</option>
              ${data.object_types.map((t) => `<option value="${esc(t)}" ${sel(t, params.object_type)}>${esc(t)}</option>`).join('')}
            </select>
            <button type="submit" class="btn btn-sm btn-primary">Filter</button>
            ${params.action || params.object_type ? '<a href="#/activity" class="btn btn-sm btn-outline-secondary">Clear</a>' : ''}
          </form>
        </div>
        <div class="card-body p-0">
          ${data.results.length ? `
          <table class="table table-hover mb-0">
            <thead><tr style="background:#f8fafc;">${th('TIME')}${th('USER')}${th('ACTION')}${th('TYPE')}${th('OBJECT')}</tr></thead>
            <tbody>
              ${data.results.map((log) => `
              <tr>
                <td style="font-size:.8rem;color:#6b7280;white-space:nowrap;">${esc(log.time)}</td>
                <td style="font-size:.875rem;font-weight:500;">${esc(log.user || '—')}</td>
                <td>${actionBadge(log.action)}</td>
                <td style="font-size:.875rem;color:#1B4F72;">${esc(log.object_type)}</td>
                <td style="font-size:.875rem;">${esc(trunc(log.object_str, 60))}</td>
              </tr>`).join('')}
            </tbody>
          </table>` : `
          <div class="text-center py-5 text-muted">
            <i class="fas fa-history fa-3x mb-3 opacity-25"></i>
            <p>No activity recorded yet.</p>
          </div>`}
        </div>
        ${data.num_pages > 1 ? `
        <div class="card-footer d-flex justify-content-center">
          <nav><ul class="pagination pagination-sm mb-0">
            ${data.page > 1 ? `<li class="page-item"><a class="page-link" href="#/activity${qs({ ...filters, page: data.page - 1 })}">«</a></li>` : ''}
            <li class="page-item disabled"><span class="page-link">${data.page} / ${data.num_pages}</span></li>
            ${data.page < data.num_pages ? `<li class="page-item"><a class="page-link" href="#/activity${qs({ ...filters, page: data.page + 1 })}">»</a></li>` : ''}
          </ul></nav>
        </div>` : ''}
      </div>`,
  });
  $('#logFilter').addEventListener('submit', (e) => {
    e.preventDefault();
    go(`#/activity${qs(Object.fromEntries(new FormData(e.target)))}`);
  });
}

async function viewAccess() {
  const { users } = await Api.get('/api/activity/access/');
  const th = (t) => `<th style="font-size:.75rem;color:#6b7280;font-weight:600;padding:10px 16px;">${t}</th>`;
  const role = {
    superuser: '<span class="badge" style="background:#ede9fe;color:#5b21b6;">Superuser</span>',
    staff: '<span class="badge" style="background:#dbeafe;color:#1e40af;">Staff</span>',
    user: '<span class="badge" style="background:#f3f4f6;color:#374151;">User</span>',
  };
  const ok = (t) => `<span class="badge" style="background:#d1fae5;color:#065f46;"><i class="fas fa-check me-1"></i>${t}</span>`;
  render({
    title: 'Activity Log Access',
    docTitle: 'Manage Activity Log Access',
    body: `
      <div class="card">
        <div class="card-header d-flex align-items-center justify-content-between" style="background:#fff; border-bottom:2px solid #e8f0f7;">
          <span style="color:#1B4F72;"><i class="fas fa-user-shield me-2"></i>Activity Log Access Control</span>
          <span class="text-muted" style="font-size:.8rem;">${users.length} user(s)</span>
        </div>
        <div class="card-body p-0">
          <table class="table table-hover mb-0">
            <thead><tr style="background:#f8fafc;">${th('USERNAME')}${th('EMAIL')}${th('ROLE')}${th('LOG ACCESS')}${th('ACTION')}</tr></thead>
            <tbody>
              ${users.map((u) => {
                const always = u.role !== 'user';
                return `
              <tr>
                <td style="font-weight:500;">${esc(u.name)}</td>
                <td style="font-size:.875rem;color:#6b7280;">—</td>
                <td>${role[u.role]}</td>
                <td>${always ? ok('Always') : u.has_access ? ok('Granted')
                  : '<span class="badge" style="background:#fee2e2;color:#991b1b;"><i class="fas fa-times me-1"></i>No Access</span>'}</td>
                <td>${always ? '<span class="text-muted" style="font-size:.8rem;">N/A</span>' : u.has_access
                  ? `<button type="button" class="btn btn-sm btn-outline-danger" data-user="${u.id}" data-action="revoke"><i class="fas fa-ban me-1"></i>Revoke</button>`
                  : `<button type="button" class="btn btn-sm btn-success" data-user="${u.id}" data-action="grant"><i class="fas fa-key me-1"></i>Grant Access</button>`}</td>
              </tr>`;
              }).join('') || '<tr><td colspan="5" class="text-center py-4 text-muted">No users found.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>`,
  });
  $$('[data-action]').forEach((btn) => btn.addEventListener('click', async () => {
    btn.disabled = true;
    try {
      const res = await Api.post('/api/activity/access/', { user_id: btn.dataset.user, action: btn.dataset.action });
      flash(res.message);
    } catch (e) {
      flash(e.message, 'danger');
    }
    route();
  }));
}

/* ----------------------------------------------------------------- router */

// [pattern, view(match, params), sidebar item, {admin}]
const routes = [
  [/^\/$/, viewDashboard, 'dashboard'],
  [/^\/hospitals$/, viewHospitals, 'hospitals'],
  [/^\/hospitals\/new$/, () => viewHospitalForm(null), 'hospitals', { admin: true }],
  [/^\/hospitals\/(\d+)$/, (m) => viewHospital(m[1]), 'hospitals'],
  [/^\/hospitals\/(\d+)\/edit$/, (m) => viewHospitalForm(m[1]), 'hospitals', { admin: true }],
  [/^\/departments$/, viewDepartments, 'departments'],
  [/^\/departments\/new$/, (m, p) => viewDepartmentForm(null, p), 'departments', { admin: true }],
  [/^\/departments\/(\d+)\/edit$/, (m, p) => viewDepartmentForm(m[1], p), 'departments', { admin: true }],
  [/^\/units$/, viewUnits, 'units'],
  [/^\/units\/new$/, (m, p) => viewUnitForm(null, p), 'units', { admin: true }],
  [/^\/units\/(\d+)\/edit$/, (m, p) => viewUnitForm(m[1], p), 'units', { admin: true }],
  [/^\/staff$/, viewStaff, 'staff'],
  [/^\/staff\/new$/, (m, p) => viewStaffForm(null, p), 'staff'],
  [/^\/staff\/(\d+)\/edit$/, (m, p) => viewStaffForm(m[1], p), 'staff'],
  [/^\/staff\/(\d+)\/availability$/, (m) => viewAvailability(m[1]), 'staff'],
  [/^\/rosters$/, viewRosters, 'rosters'],
  [/^\/rosters\/generate$/, viewGenerate, 'generate'],
  [/^\/rosters\/(\d+)$/, (m) => viewRoster(m[1]), null],
  [/^\/activity$/, viewActivity, 'activity'],
  [/^\/activity\/access$/, viewAccess, 'access', { admin: true }],
  ...['hospitals', 'departments', 'units', 'staff', 'rosters'].map((type) => [
    new RegExp(`^/${type}/(\\d+)/delete$`), (m) => viewDelete(type, m[1]),
    type === 'rosters' ? null : type, { admin: ['hospitals', 'departments', 'units'].includes(type) },
  ]),
];

function parseHash(hash) {
  const [path, query = ''] = hash.replace(/^#/, '').split('?');
  return { path: path || '/', params: Object.fromEntries(new URLSearchParams(query)) };
}

async function route() {
  const { path, params } = parseHash(location.hash);
  if (!me) {
    if (path === '/register') return viewRegister();
    if (path !== '/login') sessionStorage.setItem('next', location.hash || '#/');
    return path === '/login' ? viewLogin() : go('#/login');
  }
  if (path === '/login' || path === '/register') return go('#/');

  for (const [re, view, nav, opts = {}] of routes) {
    const m = path.match(re);
    if (!m) continue;
    if (opts.admin && !me.is_admin) {
      flash('Admin access required.', 'danger');
      return go('#/');
    }
    $$('#sidebar-nav .nav-link').forEach((a) => a.classList.toggle('active', a.dataset.nav === nav));
    loading();
    try {
      await view(m, params);
    } catch (e) {
      if (e.status === 401) return;
      if (e.status === 403) { flash(e.message, 'danger'); return go('#/'); }
      render({ title: 'Error', body: `<div class="alert alert-danger"><i class="fas fa-exclamation-circle me-2"></i>${esc(e.message)}</div>` });
    }
    return;
  }
  go('#/');
}

/* ------------------------------------------------------------------- boot */

/* A failed save from a click handler (delete, grant, cell edit) shows atop the
 * page instead of vanishing into the console. */
window.addEventListener('unhandledrejection', (e) => {
  if (!(e.reason instanceof Api.ApiError) || e.reason.status === 401) return;
  e.preventDefault();
  $$('.modal.show').forEach((m) => bootstrap.Modal.getInstance(m)?.hide());
  flash(e.reason.message, 'danger');
  $('#main').insertAdjacentHTML('afterbegin', flashHtml());
  window.scrollTo(0, 0);
});

async function boot() {
  Sidebar.init();
  Idle.init();
  $('#logoutBtn').addEventListener('click', () => { Idle.stop(); logout(); });
  // Session expired mid-use: back to sign-in, then back here afterwards.
  Api.onUnauthorized = () => {
    if (!me) return;
    me = null;
    sessionStorage.setItem('next', location.hash || '#/');
    go('#/login');
  };
  try {
    me = await Api.get('/api/auth/me/');
    showShell();
    Idle.start();
  } catch { /* signed out */ }
  window.addEventListener('hashchange', route);
  route();
}

if (typeof document !== 'undefined' && document.getElementById('main')) boot();
