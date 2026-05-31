/**
 * List-filter persistence helper.
 *
 * Lets a list page (e.g. /leads, /quotes, /tally) remember its active
 * filters across navigation — user clicks a row → views detail → comes
 * back → still sees the same filtered view.
 *
 * Usage from a Jinja template:
 *   <script src="{{ url_for('static', filename='js/list_filter_persistence.js') }}"></script>
 *   <script>
 *     ListFilterPersist.init({
 *       key: 'leadfy_filter_params',
 *       resetSelector: '.js-clear-filters',
 *     });
 *   </script>
 *
 * Mark the explicit "Clear filters" button with class `js-clear-filters`.
 * Don't rely on matching by href — sidebar nav links to the same page
 * also share that href and clear the storage by accident (the previous
 * leadfy implementation hit this bug).
 *
 * How it works:
 *   - On page load, if the URL has no query string AND sessionStorage
 *     has saved filters → location.replace() to the saved URL.
 *   - On page load, if the URL has a query string → save it.
 *   - When the user clicks a `.js-clear-filters` element → remove from
 *     sessionStorage and let the navigation continue (the button itself
 *     usually links to the bare list URL).
 *
 * Each list page uses its own `key` so they don't collide.
 */
(function (global) {
  'use strict'

  function init(opts) {
    if (!opts || !opts.key) {
      console.warn('[list-filter-persist] init() needs at least { key }')
      return
    }
    const KEY = opts.key
    const RESET_SELECTOR = opts.resetSelector || '.js-clear-filters'

    const params = window.location.search

    if (!params || params === '?') {
      // Bare URL — restore the most recently saved filter set, if any.
      const saved = sessionStorage.getItem(KEY)
      if (saved && saved !== '?' && saved !== '') {
        window.location.replace(window.location.pathname + saved)
        return // restore is in progress; nothing else to do
      }
    } else {
      // Page loaded with filters — remember them for the next visit.
      sessionStorage.setItem(KEY, params)
    }

    // Explicit "Clear filters" elements — wipe storage on click.
    document.querySelectorAll(RESET_SELECTOR).forEach(function (el) {
      el.addEventListener('click', function () {
        sessionStorage.removeItem(KEY)
      })
    })
  }

  global.ListFilterPersist = { init: init }
})(window)
