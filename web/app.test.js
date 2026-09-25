/* Self-check for app.js's pure helpers: truncation, query strings, hash
 * parsing, filter-bar links. Run: node web/app.test.js
 *
 * ponytail: source sliced out of app.js — the app loads with <script> tags
 * and has no build step to import from. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const slice = (from, to) => {
  const a = src.indexOf(from);
  const b = src.indexOf(to, a);
  assert.ok(a >= 0 && b > a, `block not found: ${from}`);
  return src.slice(a, b);
};
const code = slice('const $ = ', 'let me = null;')
  + slice('function filterBarHtml(', 'const ACTION_BADGES')
  + slice('function parseHash(', 'async function route()');
const { trunc, qs, parseHash, filterBarHtml } = new Function(
  `${code}; return { trunc, qs, parseHash, filterBarHtml };`)();

// Django truncatechars: n characters including the ellipsis.
assert.strictEqual(trunc('ABCDEF', 4), 'ABC…');
assert.strictEqual(trunc('ABCD', 4), 'ABCD');
assert.strictEqual(trunc(null, 4), '');

assert.strictEqual(qs({ a: 1, b: '', c: null, d: undefined }), '?a=1');
assert.strictEqual(qs({}), '');

assert.deepStrictEqual(parseHash(''), { path: '/', params: {} });
assert.deepStrictEqual(parseHash('#/staff?hospital=2&page=3'), { path: '/staff', params: { hospital: '2', page: '3' } });

// Picking a department keeps the hospital and drops unit + page.
const html = filterBarHtml('Department:', '/staff', { hospital: '2', dept: '5', unit: '9', page: '2' },
  'dept', ['hospital'], [{ id: 5, department_name: 'PHARM' }], (d) => d.department_name);
assert.ok(html.includes('href="#/staff?hospital=2&dept=5" class="btn btn-sm btn-primary"'), html);
assert.ok(html.includes('href="#/staff?hospital=2" class="btn btn-sm btn-outline-secondary">All'), html);

console.log('app.test.js: ok');
