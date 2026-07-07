(function () {
    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute("content") : "";
    }

    window.csrfFetch = function (url, options) {
        options = options || {};
        options.headers = options.headers || {};
        if (!options.headers["X-CSRFToken"]) {
            options.headers["X-CSRFToken"] = getCsrfToken();
        }
        return fetch(url, options);
    };

    function toggleTheme() {
        var html = document.documentElement;
        var icon = document.getElementById("themeIcon");
        if (html.getAttribute("data-bs-theme") === "dark") {
            html.removeAttribute("data-bs-theme");
            html.removeAttribute("data-theme");
            if (icon) icon.className = "bi bi-moon-fill";
            localStorage.setItem("theme", "light");
        } else {
            html.setAttribute("data-bs-theme", "dark");
            if (icon) icon.className = "bi bi-sun-fill";
            localStorage.setItem("theme", "dark");
        }
    }

    var savedTheme = localStorage.getItem("theme");
    if (savedTheme === "dark") {
        document.documentElement.setAttribute("data-bs-theme", "dark");
        var themeIcon = document.getElementById("themeIcon");
        if (themeIcon) themeIcon.className = "bi bi-sun-fill";
    }

    var scrollBtn = document.getElementById("scrollTopBtn");
    if (scrollBtn) {
        window.addEventListener("scroll", function () {
            if (window.pageYOffset > 300) {
                scrollBtn.classList.add("visible");
            } else {
                scrollBtn.classList.remove("visible");
            }
        });
        scrollBtn.addEventListener("click", function () {
            window.scrollTo({ top: 0, behavior: "smooth" });
        });
    }

    var themeToggleBtn = document.getElementById("themeToggleBtn");
    if (themeToggleBtn) {
        themeToggleBtn.addEventListener("click", toggleTheme);
    }

    function showLoading() {
        var overlay = document.getElementById("loadingOverlay");
        if (overlay) overlay.classList.add("is-visible");
    }

    function hideLoading() {
        var overlay = document.getElementById("loadingOverlay");
        if (overlay) overlay.classList.remove("is-visible");
    }

    window.toggleTheme = toggleTheme;
    window.showLoading = showLoading;
    window.hideLoading = hideLoading;
    hideLoading();

    setTimeout(function () {
        var alerts = document.querySelectorAll(".alert");
        for (var i = 0; i < alerts.length; i++) {
            if (typeof bootstrap !== "undefined" && bootstrap.Alert) {
                var bsAlert = new bootstrap.Alert(alerts[i]);
                bsAlert.close();
            }
        }
    }, 5000);

    var forms = document.querySelectorAll("form:not([data-ajax])");
    for (var j = 0; j < forms.length; j++) {
        forms[j].addEventListener("submit", function () {
            if (this.dataset.ajax === "true") return;
            var btn = this.querySelector('button[type="submit"]');
            if (btn && !btn.disabled) {
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Isleniyor...';
                showLoading();
            }
        });
    }
})();
