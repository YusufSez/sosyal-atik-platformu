(function () {
    const searchInput = document.getElementById("report-live-search");
    const form = document.getElementById("report-filter-form");
    if (!searchInput || !form) return;

    let timer = null;
    searchInput.addEventListener("input", function () {
        clearTimeout(timer);
        timer = setTimeout(function () {
            if (typeof form.requestSubmit === "function") {
                form.requestSubmit();
            } else {
                form.submit();
            }
        }, 400);
    });
})();
