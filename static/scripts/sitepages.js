// Admin > Pages: save each switch immediately and add/remove its sidebar entry.
(function () {
    var form = document.getElementById("pages-form");
    if (!form) return;
    var nav = document.querySelector("#drawer-icons nav");
    var error = document.getElementById("pages-error");
    var csrf = form.querySelector("input[name=csrfmiddlewaretoken]").value;

    function showError(text) {
        error.querySelector(".p-notification__message").textContent = text;
        error.classList.toggle("u-hide", !text);
    }

    function navItem(slug) {
        return nav && nav.querySelector('li[data-page-slug="' + slug + '"]');
    }

    function buildItem(row) {
        var li = document.createElement("li");
        li.className = "p-side-navigation__item";
        li.dataset.pageSlug = row.dataset.slug;
        var a = document.createElement("a");
        a.className = "p-side-navigation__link";
        a.href = row.dataset.url || "#";
        var icon = document.createElement("i");
        icon.className = "p-icon--" + row.dataset.icon + " is-light p-side-navigation__icon";
        var label = document.createElement("span");
        label.className = "p-side-navigation__label";
        label.textContent = row.dataset.label;
        a.append(icon, label);
        li.append(a);
        return li;
    }

    function setNav(row, enabled) {
        if (!nav) return;
        var existing = navItem(row.dataset.slug);
        if (!enabled) {
            if (existing) existing.remove();
            return;
        }
        if (existing) return;
        // Keep the registry order: insert before the next shown page, else before Admin.
        var before = null;
        for (var next = row.nextElementSibling; next && !before; next = next.nextElementSibling) {
            before = navItem(next.dataset.slug);
        }
        before = before || nav.querySelector("li[data-site-admin-nav]");
        nav.insertBefore(buildItem(row), before);
    }

    form.addEventListener("change", function (event) {
        var input = event.target;
        if (!input.matches("input[name=enabled]")) return;
        var row = input.closest("tr");
        var wanted = input.checked;
        input.disabled = true;
        var body = new URLSearchParams({ enabled: wanted ? "true" : "false" });
        fetch(row.dataset.toggleUrl, {
            method: "POST",
            headers: { "X-CSRFToken": csrf },
            body: body,
            credentials: "same-origin",
        })
            .then(function (response) {
                if (!response.ok) throw new Error(response.status + " " + response.statusText);
                return response.json();
            })
            .then(function (data) {
                input.checked = data.enabled;
                setNav(row, data.enabled);
                showError("");
            })
            .catch(function (err) {
                input.checked = !wanted;
                showError("Could not update " + row.dataset.label + ": " + err.message);
            })
            .finally(function () {
                input.disabled = false;
            });
    });
})();
