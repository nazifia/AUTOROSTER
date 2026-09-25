/* Client for the AutoRoster JSON API (roster/views.py, accounts/views.py).
 * Same origin as the page, so auth is the Django session cookie; writes carry
 * the CSRF token from the csrftoken cookie the index view sets. Bodies go as
 * form data because the server validates them with its Django forms. */
'use strict';

const Api = (() => {
  class ApiError extends Error {
    constructor(message, status, errors) {
      super(message);
      this.status = status;
      this.errors = errors || null; // {field: [messages]} from a failed form
    }
  }

  // Read fresh every call: Django rotates the token on sign-in.
  const csrf = () => decodeURIComponent((document.cookie.match(/(?:^|; )csrftoken=([^;]*)/) || [])[1] || '');

  let onUnauthorized = () => {};

  function formData(body) {
    if (body instanceof FormData) return body;
    const fd = new FormData();
    for (const [k, v] of Object.entries(body || {})) {
      if (v !== undefined && v !== null && v !== '') fd.append(k, v);
    }
    return fd;
  }

  async function request(method, path, body) {
    const res = await fetch(path, {
      method,
      credentials: 'same-origin',
      headers: { 'X-CSRFToken': csrf() },
      body,
    });
    let data = null;
    try { data = await res.json(); } catch { /* HTML 404 page, empty body */ }
    if (res.status === 401) onUnauthorized();
    if (!res.ok) {
      const message = data?.error || (data?.errors ? 'Please correct the errors below.' : `Request failed (${res.status})`);
      throw new ApiError(message, res.status, data?.errors);
    }
    return data;
  }

  return {
    ApiError,
    set onUnauthorized(fn) { onUnauthorized = fn; },
    get: (path, query) => {
      const q = new URLSearchParams(Object.entries(query || {}).filter(([, v]) => v !== undefined && v !== null && v !== ''));
      return request('GET', q.toString() ? `${path}?${q}` : path);
    },
    post: (path, body) => request('POST', path, formData(body)),
    del: (path) => request('DELETE', path),
  };
})();
