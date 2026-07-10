(function (global) {
  function isNearBottom(scrollEl, threshold) {
    if (!scrollEl) return true;
    var t = typeof threshold === "number" ? threshold : 80;
    return scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight < t;
  }

  global.MessageScrollHelper = {
    isNearBottom: isNearBottom,
  };
})(typeof window !== "undefined" ? window : globalThis);
