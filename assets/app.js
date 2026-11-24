/* GWENT glossary — theme, search, scrollspy, mobile drawer */
(function () {
  "use strict";

  var root = document.documentElement;
  var body = document.body;

  /* ---------- theme ---------- */
  var THEME_KEY = "gwent-glossary-theme";
  var themeToggle = document.getElementById("themeToggle");

  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    if (themeToggle) {
      themeToggle.textContent = theme === "dark" ? "☀" : "☾";
      themeToggle.setAttribute(
        "aria-label",
        theme === "dark" ? "Включить светлую тему" : "Включить тёмную тему"
      );
    }
  }

  var stored = null;
  try {
    stored = localStorage.getItem(THEME_KEY);
  } catch (err) {
    stored = null;
  }
  if (!stored) {
    stored = window.matchMedia("(prefers-color-scheme: light)").matches
      ? "light"
      : "dark";
  }
  applyTheme(stored);

  if (themeToggle) {
    themeToggle.addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      applyTheme(next);
      try {
        localStorage.setItem(THEME_KEY, next);
      } catch (err) {
        /* storage may be unavailable */
      }
    });
  }

  /* ---------- mobile drawer ---------- */
  var sidebar = document.getElementById("sidebar");
  var tocToggle = document.getElementById("tocToggle");

  function closeDrawer() {
    if (!sidebar || !tocToggle) return;
    sidebar.classList.remove("is-open");
    tocToggle.setAttribute("aria-expanded", "false");
  }

  if (sidebar && tocToggle) {
    tocToggle.addEventListener("click", function () {
      var open = sidebar.classList.toggle("is-open");
      tocToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });

    sidebar.addEventListener("click", function (event) {
      if (event.target.closest("a")) closeDrawer();
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") closeDrawer();
    });
  }

  /* ---------- search ---------- */
  var input = document.getElementById("search");
  var clearBtn = document.getElementById("searchClear");
  var status = document.getElementById("searchStatus");
  var articles = Array.prototype.slice.call(document.querySelectorAll(".term"));
  var tocLinks = Array.prototype.slice.call(document.querySelectorAll(".toc a"));
  var tocGroups = Array.prototype.slice.call(document.querySelectorAll(".toc-group"));
  var sections = Array.prototype.slice.call(document.querySelectorAll(".group"));

  var index = articles.map(function (article) {
    return {
      el: article,
      slug: article.id,
      text: normalize(article.textContent || "")
    };
  });

  var tocBySlug = {};
  tocLinks.forEach(function (link) {
    tocBySlug[link.getAttribute("data-slug")] = link;
  });

  function normalize(value) {
    return value.toLowerCase().replace(/ё/g, "е").replace(/\s+/g, " ").trim();
  }

  function runSearch(rawQuery) {
    var query = normalize(rawQuery);
    var terms = query.split(" ").filter(Boolean);
    var matches = 0;

    index.forEach(function (item) {
      var hit =
        terms.length === 0 ||
        terms.every(function (term) {
          return item.text.indexOf(term) !== -1;
        });
      item.el.hidden = !hit;
      if (hit) matches += 1;

      var link = tocBySlug[item.slug];
      if (link) {
        link.parentNode.hidden = !hit;
        link.classList.remove("is-active");
      }
    });

    sections.forEach(function (section) {
      var visible = section.querySelector(".term:not([hidden])");
      section.hidden = !visible;
    });

    tocGroups.forEach(function (group) {
      var visible = group.querySelector("li:not([hidden])");
      group.hidden = !visible;
    });

    if (status) {
      if (terms.length === 0) {
        status.hidden = true;
        status.textContent = "";
      } else {
        status.hidden = false;
        status.textContent =
          matches === 0
            ? "Ничего не найдено"
            : "Найдено: " + matches;
      }
    }

    if (clearBtn) clearBtn.hidden = rawQuery.length === 0;
  }

  if (input) {
    var timer = null;
    input.addEventListener("input", function () {
      window.clearTimeout(timer);
      var value = input.value;
      timer = window.setTimeout(function () {
        runSearch(value);
      }, 90);
    });

    input.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        input.value = "";
        runSearch("");
      }
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", function () {
      if (!input) return;
      input.value = "";
      input.focus();
      runSearch("");
    });
  }

  document.addEventListener("keydown", function (event) {
    if (event.key === "/" && document.activeElement !== input) {
      event.preventDefault();
      if (input) input.focus();
    }
  });

  /* ---------- scrollspy ---------- */
  if ("IntersectionObserver" in window && articles.length) {
    var visible = new Map();

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          visible.set(entry.target.id, entry.isIntersecting);
        });

        var current = null;
        for (var i = 0; i < articles.length; i += 1) {
          if (visible.get(articles[i].id)) {
            current = articles[i].id;
            break;
          }
        }
        if (!current) return;

        tocLinks.forEach(function (link) {
          link.classList.toggle(
            "is-active",
            link.getAttribute("data-slug") === current
          );
        });

        var active = tocBySlug[current];
        if (active && sidebar && sidebar.classList.contains("is-open")) return;
        if (active) {
          var box = active.getBoundingClientRect();
          var panel = sidebar ? sidebar.getBoundingClientRect() : null;
          if (panel && (box.top < panel.top + 40 || box.bottom > panel.bottom - 40)) {
            active.scrollIntoView({ block: "nearest" });
          }
        }
      },
      { rootMargin: "-72px 0px -65% 0px", threshold: 0 }
    );

    articles.forEach(function (article) {
      observer.observe(article);
    });
  }

  /* ---------- highlight deep-linked term ---------- */
  function highlightHash() {
    var id = window.location.hash.slice(1);
    articles.forEach(function (article) {
      article.classList.toggle("is-target", article.id === id);
    });
    if (!id) return;
    var target = document.getElementById(id);
    if (target) target.classList.add("is-target");
  }

  window.addEventListener("hashchange", highlightHash);
  highlightHash();
})();
