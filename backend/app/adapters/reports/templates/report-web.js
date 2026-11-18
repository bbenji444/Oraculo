/*
 * Vista del reporte en pantalla (ADR-0111): lo que el PDF no puede hacer.
 *
 * Lo inserta la plantilla al final de <body class="web"> con el nonce de la
 * respuesta; la política de contenido de la API no deja correr otro script
 * ni pedir nada a ningún servidor. Solo arregla esta página.
 *
 * Hace, sobre el HTML que ya armó la plantilla:
 * 1. Índice: un link por sección y por pregunta, con la sección a la vista
 *    marcada.
 * 2. Pliegues: cada pregunta se contrae o se despliega con su título.
 * 3. Filtro de noticias: por texto y por estado, con el conteo de hechos.
 * 4. Ayudas: el número exacto al pasar el mouse por barras, dona y mapa
 *    (lee los title de la plantilla y del mapa).
 * 5. Cifras que cuentan hacia arriba y links que abren en otra pestaña.
 *
 * No hace: no pide nada a la API ni guarda nada en el navegador.
 */
(function () {
  "use strict";

  var REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  // Lo que tarda en contar una cifra de la portada hasta su valor.
  var COUNT_UP_MS = 700;
  // El botón «arriba» aparece después de bajar esto.
  var TOP_BUTTON_AFTER_PX = 900;
  // Separación entre el puntero y la ayuda.
  var TIP_OFFSET_PX = 14;

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  // Para comparar sin mayúsculas ni acentos (la Ñ se vuelve N, como en el buscador).
  function normalize(text) {
    return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }

  // Texto del título sin el número de pregunta ni la insignia de IA.
  function headingText(head) {
    var copy = head.cloneNode(true);
    copy.querySelectorAll(".q-num, .badge-ai, .web-fold").forEach(function (n) {
      n.remove();
    });
    return copy.textContent.replace(/\s+/g, " ").trim();
  }

  // ------------------------------------------------------------ 5. Links
  document.querySelectorAll('a[href^="http"]').forEach(function (link) {
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  });

  // -------------------------------------------------------- 2. Pliegues
  // Lo que pertenece a un título: sus hermanos hasta el siguiente título.
  function bodyOf(head) {
    var parts = [];
    var next = head.nextElementSibling;
    while (next && !next.matches("h2")) {
      parts.push(next);
      next = next.nextElementSibling;
    }
    return parts;
  }

  var folds = [];
  var heads = Array.prototype.slice.call(document.querySelectorAll("h2.section, h2.q-title"));
  heads.forEach(function (head, index) {
    head.id = head.id || "s" + String(index + 1);
    var parts = bodyOf(head);
    if (!parts.length) return;
    var button = element("button", "web-fold");
    button.type = "button";
    button.setAttribute("aria-expanded", "true");
    button.setAttribute("aria-label", "Contraer «" + headingText(head) + "»");
    head.appendChild(button);
    head.setAttribute("data-web-head", "");
    function set(open) {
      button.setAttribute("aria-expanded", String(open));
      button.setAttribute(
        "aria-label",
        (open ? "Contraer «" : "Desplegar «") + headingText(head) + "»",
      );
      parts.forEach(function (part) {
        part.hidden = !open;
      });
    }
    head.addEventListener("click", function (event) {
      // Un link dentro del título sigue funcionando normal.
      if (event.target.closest("a")) return;
      set(button.getAttribute("aria-expanded") !== "true");
    });
    folds.push({ head: head, set: set });
  });

  function openFold(head) {
    folds.forEach(function (fold) {
      if (fold.head === head) fold.set(true);
    });
  }

  // ----------------------------------------------------------- 1. Índice
  var toc = element("nav", "web-toc");
  toc.setAttribute("aria-label", "Índice del reporte");
  toc.appendChild(element("p", "web-toc-title", "ÍNDICE"));
  var cover = document.querySelector(".cover");
  var links = [];
  function addLink(target, text, kind) {
    var link = element("a", kind, text);
    link.href = "#" + target.id;
    link.addEventListener("click", function () {
      openFold(target);
    });
    toc.appendChild(link);
    links.push({ link: link, target: target });
  }
  if (cover) {
    cover.id = "portada";
    addLink(cover, "Portada", "web-toc-group");
  }
  heads.forEach(function (head) {
    addLink(
      head,
      headingText(head),
      head.matches(".section") ? "web-toc-group" : "web-toc-question",
    );
  });
  var actions = element("div", "web-toc-actions");
  [
    ["Contraer todo", false],
    ["Desplegar todo", true],
  ].forEach(function (pair) {
    var button = element("button", "web-btn", pair[0]);
    button.type = "button";
    button.addEventListener("click", function () {
      folds.forEach(function (fold) {
        fold.set(pair[1]);
      });
    });
    actions.appendChild(button);
  });
  toc.appendChild(actions);
  document.body.insertBefore(toc, document.body.firstChild);

  // La sección a la vista se marca en el índice.
  if ("IntersectionObserver" in window) {
    var visible = new Map();
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          visible.set(entry.target, entry.isIntersecting);
        });
        var current = null;
        links.forEach(function (item) {
          if (!current && visible.get(item.target)) current = item;
        });
        if (!current) return;
        links.forEach(function (item) {
          if (item === current) item.link.setAttribute("aria-current", "true");
          else item.link.removeAttribute("aria-current");
        });
      },
      { rootMargin: "0px 0px -60% 0px" },
    );
    links.forEach(function (item) {
      observer.observe(item.target);
    });
  }

  // ----------------------------------------------- 3. Filtro de noticias
  var news = document.querySelector("section.news");
  var states = news ? Array.prototype.slice.call(news.querySelectorAll(".state")) : [];
  if (states.length) {
    var filter = element("div", "web-filter");
    var search = element("input");
    search.type = "search";
    search.placeholder = "Buscar en las noticias (título o medio)…";
    search.setAttribute("aria-label", "Buscar en las noticias");
    var select = element("select");
    select.setAttribute("aria-label", "Estado");
    select.appendChild(new Option("Todos los estados", ""));
    var stateName = function (state) {
      var title = state.querySelector(".state-title");
      return title && title.firstChild ? title.firstChild.textContent.trim() : "";
    };
    states.forEach(function (state) {
      select.appendChild(new Option(stateName(state), stateName(state)));
    });
    var count = element("span", "web-filter-count");
    count.setAttribute("aria-live", "polite");
    filter.append(search, select, count);
    var anchor = news.querySelector("p.muted") || news.querySelector("h2");
    anchor.after(filter);

    var apply = function () {
      var words = normalize(search.value).split(/\s+/).filter(Boolean);
      var chosen = select.value;
      var total = 0;
      states.forEach(function (state) {
        var stateShown = 0;
        if (!chosen || stateName(state) === chosen) {
          state.querySelectorAll("table.index").forEach(function (table) {
            var shown = 0;
            table.querySelectorAll("tr").forEach(function (row) {
              var text = normalize(row.textContent);
              var match = words.every(function (word) {
                return text.indexOf(word) !== -1;
              });
              row.hidden = !match;
              if (match) shown += 1;
            });
            table.hidden = shown === 0;
            var title = table.previousElementSibling;
            if (title && title.matches(".category-title")) title.hidden = shown === 0;
            stateShown += shown;
          });
        }
        state.hidden = stateShown === 0;
        total += stateShown;
      });
      count.textContent = total === 1 ? "1 hecho" : String(total) + " hechos";
    };
    search.addEventListener("input", apply);
    select.addEventListener("change", apply);
    apply();
  }

  // ----------------------------------------------------------- 4. Ayudas
  // Los title nativos tardan en salir y no se ven igual en todos lados: se
  // pasan a data-tip y se muestra una ayuda propia junto al puntero.
  document.querySelectorAll("[title]").forEach(function (node) {
    node.setAttribute("data-tip", node.getAttribute("title"));
    node.removeAttribute("title");
  });
  document.querySelectorAll("svg title").forEach(function (title) {
    var owner = title.parentNode;
    // El title del SVG completo describe la gráfica, no un dato.
    if (owner.tagName.toLowerCase() !== "svg") {
      owner.setAttribute("data-tip", title.textContent);
    }
    title.remove();
  });
  var tip = element("div", "web-tip");
  tip.hidden = true;
  tip.setAttribute("role", "tooltip");
  document.body.appendChild(tip);
  document.addEventListener("mousemove", function (event) {
    var target = event.target.closest ? event.target.closest("[data-tip]") : null;
    if (!target) {
      tip.hidden = true;
      return;
    }
    tip.textContent = target.getAttribute("data-tip");
    tip.hidden = false;
    var x = event.clientX + TIP_OFFSET_PX;
    var y = event.clientY + TIP_OFFSET_PX;
    // Que no se salga por la derecha ni por abajo.
    x = Math.min(x, window.innerWidth - tip.offsetWidth - 8);
    y = Math.min(y, window.innerHeight - tip.offsetHeight - 8);
    tip.style.left = String(x) + "px";
    tip.style.top = String(y) + "px";
  });
  document.addEventListener("mouseleave", function () {
    tip.hidden = true;
  });
  // Al desplazarse, lo que quedó bajo el puntero ya es otra cosa.
  window.addEventListener(
    "scroll",
    function () {
      tip.hidden = true;
    },
    { passive: true },
  );

  // ------------------------------------------- 5. Cifras y botón arriba
  if (!REDUCED_MOTION) {
    document.querySelectorAll(".cover-kpis strong, .kpi strong").forEach(function (node) {
      var goal = Number(node.textContent.trim());
      if (!Number.isInteger(goal) || goal <= 0) return;
      var start = performance.now();
      var step = function (now) {
        var progress = Math.min(1, (now - start) / COUNT_UP_MS);
        node.textContent = String(Math.round(goal * progress));
        if (progress < 1) requestAnimationFrame(step);
      };
      node.textContent = "0";
      requestAnimationFrame(step);
    });
  }

  var top = element("button", "web-top", "↑");
  top.type = "button";
  top.hidden = true;
  top.setAttribute("aria-label", "Volver al inicio del reporte");
  top.addEventListener("click", function () {
    window.scrollTo({ top: 0, behavior: REDUCED_MOTION ? "auto" : "smooth" });
  });
  document.body.appendChild(top);
  window.addEventListener(
    "scroll",
    function () {
      top.hidden = window.scrollY < TOP_BUTTON_AFTER_PX;
    },
    { passive: true },
  );
})();
