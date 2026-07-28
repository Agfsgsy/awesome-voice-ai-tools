(() => {
  'use strict';
  if (window.__ibnWaqadiResponseBodyGuard) return;
  window.__ibnWaqadiResponseBodyGuard = true;

  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await nativeFetch(...args);
    // The preserved 6.2 pages try response.json(), then response.text() on a
    // non-JSON error. JSON parsing normally consumes the stream. Read JSON from
    // a clone so the original response remains available for the text fallback.
    const jsonCopy = response.clone();
    response.json = () => jsonCopy.json();
    return response;
  };
})();
