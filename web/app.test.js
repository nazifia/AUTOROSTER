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
  + slice('function parseHash(', 'async function route()')
  + slice('const exportUrl = ', '/* "3 of 12 rosters')
  + slice('function rosterSearchStatus(', 'async function viewRosters(');
const { trunc, qs, parseHash, filterBarHtml, searchTerms, matchesSearch, rosterRowsHtml, rosterSearchStatus } = new Function(
  `${code}; return { trunc, qs, parseHash, filterBarHtml, searchTerms, matchesSearch, rosterRowsHtml, rosterSearchStatus };`)();

// Django truncatechars: n characters including the ellipsis.
assert.strictEqual(trunc('ABCDEF', 4), 'ABC…');
assert.strictEqual(trunc('ABCD', 4), 'ABCD');
assert.strictEqual(trunc(null, 4), '');

assert.strictEqual(qs({ a: 1, b: '', c: null, d: undefined }), '?a=1');
assert.strictEqual(qs({}), '');

// Unit search: case-insensitive, every word anywhere in the haystack.
assert.deepStrictEqual(searchTerms('  NHIA   Pharmacy '), ['nhia', 'pharmacy']);
assert.deepStrictEqual(searchTerms('   '), []);
const nhia = 'nhia pharmacy pharmacy department — nhia pharmacy fth katsina';
assert.ok(matchesSearch(nhia, searchTerms('nhia')));
assert.ok(matchesSearch(nhia, searchTerms('KATSINA pharmacy')), 'order-independent');
assert.ok(!matchesSearch(nhia, searchTerms('nhia emergency')), 'all words must match');
assert.ok(matchesSearch(nhia, searchTerms('  ')), 'empty query matches everything');

// Roster list search: counts while filtering, a plain empty state when not.
assert.strictEqual(rosterSearchStatus({ count: 3, total: 12 }, 'nhia'), '3 of 12 rosters matching “nhia”');
assert.strictEqual(rosterSearchStatus({ count: 1, total: 1 }, 'july'), '1 of 1 roster matching “july”');
assert.strictEqual(rosterSearchStatus({ count: 2 }, 'x'), '2 of 2 rosters matching “x”', 'older API without total');
assert.strictEqual(rosterSearchStatus({ count: 0, total: 12 }, 'zzz'), 'No rosters match “zzz”.');
assert.strictEqual(rosterSearchStatus({ count: 5, total: 5 }, ''), '');
assert.ok(rosterRowsHtml({ results: [] }, 'zzz').includes('No rosters match “zzz”.'));
assert.ok(rosterRowsHtml({ results: [] }, '').includes('No rosters yet.'));

assert.deepStrictEqual(parseHash(''), { path: '/', params: {} });
assert.deepStrictEqual(parseHash('#/staff?hospital=2&page=3'), { path: '/staff', params: { hospital: '2', page: '3' } });

// Picking a department keeps the hospital and drops unit + page.
const html = filterBarHtml('Department:', '/staff', { hospital: '2', dept: '5', unit: '9', page: '2' },
  'dept', ['hospital'], [{ id: 5, department_name: 'PHARM' }], (d) => d.department_name);
assert.ok(html.includes('href="#/staff?hospital=2&dept=5" class="btn btn-sm btn-primary"'), html);
assert.ok(html.includes('href="#/staff?hospital=2" class="btn btn-sm btn-outline-secondary">All'), html);

console.log('app.test.js: ok');
