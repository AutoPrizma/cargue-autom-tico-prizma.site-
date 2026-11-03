/* Cargue Prizma Pro: comportamiento comun de todas las paginas.
   - Tema claro/oscuro (se recuerda en este navegador).
   - Menus desplegables (usuario y acciones de las tablas).
   - Copiar al portapapeles con aviso temporal.
   - Dialogos (Ver guia).
   - Estado real del servicio (/estado-servicio).
   - Tablas: buscar, filtrar, ordenar y paginar en el navegador. */
(function () {
  "use strict";

  var CLAVE_TEMA = "autoPrizmaTema";

  // ============================================================
  // TEMA
  // ============================================================
  function temaActual() {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function aplicarTema(tema) {
    document.documentElement.setAttribute("data-theme", tema);
    var texto = tema === "dark" ? "Cambiar a tema claro" : "Cambiar a tema oscuro";
    document.querySelectorAll("[data-tema-toggle]").forEach(function (boton) {
      boton.setAttribute("aria-label", texto);
      boton.title = texto;
    });
  }

  aplicarTema(temaActual());

  // Zonas de selección: anima el borde vacío y lo detiene con un archivo listo.
  function actualizarZonaArchivo(zona, archivoPresente) {
    if (!zona) return;
    zona.classList.toggle("archivo-listo", Boolean(archivoPresente));
    var input = zona.querySelector('input[type="file"]');
    zona.classList.toggle("archivo-inactivo", Boolean(input && input.disabled));
  }

  document.querySelectorAll(".dropzone, .moodle-file-drop, .moodle-label-file").forEach(function (zona) {
    var input = zona.querySelector('input[type="file"]');
    actualizarZonaArchivo(zona, Boolean(input && input.files && input.files.length));
  });

  document.addEventListener("change", function (evento) {
    var input = evento.target;
    if (!input || !input.matches || !input.matches('input[type="file"]')) return;
    var zona = input.closest(".dropzone, .moodle-file-drop, .moodle-label-file");
    if (!zona) return;
    // Deja terminar validaciones de la vista (por ejemplo, retirar un archivo inválido).
    Promise.resolve().then(function () {
      actualizarZonaArchivo(zona, Boolean(input.files && input.files.length));
    });
  });

  document.addEventListener("drop", function (evento) {
    var zona = evento.target.closest && evento.target.closest(".dropzone, .moodle-file-drop, .moodle-label-file");
    var archivos = evento.dataTransfer && evento.dataTransfer.files;
    if (zona && archivos && archivos.length) actualizarZonaArchivo(zona, true);
  });

  document.addEventListener("click", function (evento) {
    if (!evento.target.closest("[data-tema-toggle]")) return;
    var siguiente = temaActual() === "dark" ? "light" : "dark";
    try { localStorage.setItem(CLAVE_TEMA, siguiente); } catch (_) { /* sin almacenamiento */ }
    aplicarTema(siguiente);
  });

  // ============================================================
  // AVISO TEMPORAL
  // ============================================================
  var temporizadorAviso = null;

  function toast(texto) {
    var aviso = document.getElementById("toast");
    if (!aviso) {
      aviso = document.createElement("div");
      aviso.id = "toast";
      aviso.className = "toast";
      aviso.setAttribute("role", "status");
      aviso.setAttribute("aria-live", "polite");
      document.body.appendChild(aviso);
    }
    aviso.textContent = texto;
    aviso.classList.add("visible");
    clearTimeout(temporizadorAviso);
    temporizadorAviso = setTimeout(function () { aviso.classList.remove("visible"); }, 2200);
  }

  // ============================================================
  // MENUS DESPLEGABLES
  // ============================================================
  function cerrarMenus(excepto) {
    document.querySelectorAll("[data-menu]").forEach(function (menu) {
      if (menu === excepto) return;
      var lista = menu.querySelector("[data-menu-lista]");
      var boton = menu.querySelector("[data-menu-boton]");
      if (lista && !lista.hidden) {
        lista.hidden = true;
        if (boton) boton.setAttribute("aria-expanded", "false");
      }
    });
  }

  function posicionar(boton, lista) {
    // Los menus de las tablas usan posicion fija para no quedar recortados
    // por el desplazamiento horizontal de la tabla.
    var rect = boton.getBoundingClientRect();
    lista.style.left = "0px";
    lista.style.top = "0px";
    var ancho = lista.offsetWidth;
    var alto = lista.offsetHeight;
    var izquierda = Math.max(8, Math.min(rect.right - ancho, window.innerWidth - ancho - 8));
    var arriba = rect.bottom + 6;
    if (arriba + alto > window.innerHeight - 8) arriba = Math.max(8, rect.top - alto - 6);
    lista.style.left = izquierda + "px";
    lista.style.top = arriba + "px";
  }

  function abrirMenu(menu) {
    var boton = menu.querySelector("[data-menu-boton]");
    var lista = menu.querySelector("[data-menu-lista]");
    cerrarMenus(menu);
    lista.hidden = false;
    boton.setAttribute("aria-expanded", "true");
    if (lista.classList.contains("flotante")) posicionar(boton, lista);
  }

  document.addEventListener("click", function (evento) {
    var boton = evento.target.closest("[data-menu-boton]");
    if (boton) {
      var menu = boton.closest("[data-menu]");
      var lista = menu && menu.querySelector("[data-menu-lista]");
      if (!lista) return;
      if (lista.hidden) abrirMenu(menu); else cerrarMenus();
      return;
    }
    if (!evento.target.closest("[data-menu-lista]")) cerrarMenus();
  });

  document.addEventListener("keydown", function (evento) {
    if (evento.key !== "Escape") return;
    var abierta = document.querySelector("[data-menu-lista]:not([hidden])");
    if (!abierta) return;
    cerrarMenus();
    var boton = abierta.closest("[data-menu]").querySelector("[data-menu-boton]");
    if (boton) boton.focus();
  });

  window.addEventListener("resize", function () { cerrarMenus(); });
  window.addEventListener("scroll", function () {
    if (document.querySelector(".flotante:not([hidden])")) cerrarMenus();
  }, true);

  // ============================================================
  // COPIAR
  // ============================================================
  function copiarTexto(texto) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(texto);
    }
    return new Promise(function (resolver, rechazar) {
      var area = document.createElement("textarea");
      area.value = texto;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      try {
        if (document.execCommand("copy")) resolver(); else rechazar(new Error("copy"));
      } catch (error) {
        rechazar(error);
      } finally {
        area.remove();
      }
    });
  }

  document.addEventListener("click", function (evento) {
    var boton = evento.target.closest("[data-copiar]");
    if (!boton) return;
    var texto = boton.getAttribute("data-copiar") || "";
    if (boton.hasAttribute("data-copiar-url")) texto = new URL(texto, window.location.origin).href;
    copiarTexto(texto).then(
      function () { toast(boton.getAttribute("data-copiado") || "Copiado"); },
      function () { toast("No se pudo copiar. Selecciona el texto y cópialo a mano."); }
    );
    cerrarMenus();
  });

  // ============================================================
  // DIALOGOS
  // ============================================================
  document.addEventListener("click", function (evento) {
    var abrir = evento.target.closest("[data-abrir-dialogo]");
    if (abrir) {
      var dialogo = document.getElementById(abrir.getAttribute("data-abrir-dialogo"));
      if (dialogo && dialogo.showModal) dialogo.showModal();
      return;
    }
    var cerrar = evento.target.closest("[data-cerrar-dialogo]");
    if (cerrar) {
      var actual = cerrar.closest("dialog");
      if (actual) actual.close();
      return;
    }
    // Clic en el fondo oscuro del dialogo.
    if (evento.target.tagName === "DIALOG") evento.target.close();
  });

  // ============================================================
  // ESTADO DEL SERVICIO
  // ============================================================
  // Mismos textos que web/layout.py (_TEXTOS_ESTADO).
  var TEXTOS_ESTADO = {
    "linea": { ok: "Servicio activo", error: "Servicio con problemas", pendiente: "Comprobando servicio" },
    "chromium": { ok: "Chromium", error: "No disponible", pendiente: "Comprobando" },
    "prizma": { ok: "Estable", error: "Sin respuesta", pendiente: "Comprobando" },
    "pastilla-chromium": { ok: "Chromium activo", error: "Chromium no disponible", pendiente: "Comprobando Chromium" },
    "pastilla-prizma": { ok: "Servicio estable", error: "PRIZMA sin respuesta", pendiente: "Comprobando PRIZMA" }
  };

  function pintarEstado(clave, estado, detalle) {
    document.querySelectorAll('[data-servicio="' + clave + '"]').forEach(function (elemento) {
      elemento.setAttribute("data-estado", estado);
      var texto = elemento.querySelector("[data-texto]");
      if (texto && TEXTOS_ESTADO[clave]) texto.textContent = TEXTOS_ESTADO[clave][estado];
      if (clave !== "linea") elemento.title = detalle || "";
    });
  }

  function actualizarServicio() {
    if (!document.querySelector("[data-servicio]")) return;
    fetch("/estado-servicio", { headers: { "Accept": "application/json" }, credentials: "same-origin" })
      .then(function (respuesta) {
        if (!respuesta.ok) throw new Error("HTTP " + respuesta.status);
        return respuesta.json();
      })
      .then(function (datos) {
        var chromium = datos.chromium || {};
        var prizma = datos.prizma || {};
        var estadoChromium = chromium.ok ? "ok" : "error";
        var estadoPrizma = prizma.ok ? "ok" : "error";
        pintarEstado("chromium", estadoChromium, chromium.detalle);
        pintarEstado("pastilla-chromium", estadoChromium, chromium.detalle);
        pintarEstado("prizma", estadoPrizma, prizma.detalle);
        pintarEstado("pastilla-prizma", estadoPrizma, prizma.detalle);
        pintarEstado("linea", datos.ok ? "ok" : "error");
        document.querySelectorAll('[data-servicio="linea"]').forEach(function (linea) {
          linea.title = datos.ok ? "" : [chromium.ok ? "" : chromium.detalle, prizma.ok ? "" : prizma.detalle].filter(Boolean).join(" · ");
        });
      })
      .catch(function () { /* se reintenta en el siguiente ciclo */ });
  }

  actualizarServicio();
  setInterval(actualizarServicio, 5 * 60 * 1000);

  // ============================================================
  // TABLAS: BUSCAR, FILTRAR, ORDENAR Y PAGINAR
  // ============================================================
  var SVG_ANTERIOR = '<svg class="icono" viewBox="0 0 24 24" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>';
  var SVG_SIGUIENTE = '<svg class="icono" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>';

  function dentroDeRango(fechaIso, rango) {
    var fecha = new Date(fechaIso);
    if (isNaN(fecha.getTime())) return false;
    var ahora = new Date();
    if (rango === "hoy") return fecha.toDateString() === ahora.toDateString();
    var dias = parseInt(rango, 10);
    if (!dias) return true;
    return ahora.getTime() - fecha.getTime() <= dias * 86400000;
  }

  function valorCelda(celda) {
    if (!celda) return "";
    return celda.getAttribute("data-valor") || celda.textContent.trim();
  }

  function numerosDePagina(actual, total) {
    if (total <= 7) {
      var todas = [];
      for (var n = 1; n <= total; n++) todas.push(n);
      return todas;
    }
    var lista = [1];
    var desde = Math.max(2, actual - 1);
    var hasta = Math.min(total - 1, actual + 1);
    if (desde > 2) lista.push("…");
    for (var i = desde; i <= hasta; i++) lista.push(i);
    if (hasta < total - 1) lista.push("…");
    lista.push(total);
    return lista;
  }

  function iniciarTabla(contenedor) {
    var tabla = contenedor.querySelector("table");
    if (!tabla || !tabla.tBodies.length) return;
    var cuerpo = tabla.tBodies[0];
    var filas = Array.prototype.slice.call(cuerpo.querySelectorAll("tr[data-fila]"));
    var controles = contenedor.id
      ? Array.prototype.slice.call(document.querySelectorAll('[data-control-tabla="' + contenedor.id + '"]'))
      : [];
    var selectorTamano = contenedor.querySelector("[data-tabla-tamano]");
    var porPagina = parseInt((selectorTamano && selectorTamano.value) || contenedor.getAttribute("data-por-pagina") || "10", 10);
    var pagina = 1;
    var unidad = contenedor.getAttribute("data-unidad") || "registros";
    var columnas = tabla.tHead && tabla.tHead.rows.length ? tabla.tHead.rows[0].cells.length : 1;
    var filaSinResultados = document.createElement("tr");
    filaSinResultados.className = "fila-vacia";
    filaSinResultados.innerHTML = '<td colspan="' + columnas + '">No hay resultados con esos filtros.</td>';

    function coincide(fila) {
      for (var i = 0; i < controles.length; i++) {
        var control = controles[i];
        var valor = String(control.value || "").trim();
        if (!valor) continue;
        var tipo = control.getAttribute("data-tipo");
        if (tipo === "buscar") {
          var texto = (fila.getAttribute("data-busqueda") || fila.textContent).toLowerCase();
          if (texto.indexOf(valor.toLowerCase()) === -1) return false;
        } else if (tipo === "filtro") {
          // Un reporte con varios cursos guarda sus valores separados por "|".
          var valores = (fila.getAttribute("data-" + control.getAttribute("data-campo")) || "").split("|");
          if (valores.indexOf(valor) === -1) return false;
        } else if (tipo === "fecha") {
          if (!dentroDeRango(fila.getAttribute("data-fecha"), valor)) return false;
        }
      }
      return true;
    }

    function pintarPaginas(totalPaginas) {
      var nav = contenedor.querySelector("[data-tabla-paginas]");
      if (!nav) return;
      var html = '<button type="button" data-pagina="' + (pagina - 1) + '" aria-label="Página anterior"'
        + (pagina <= 1 ? " disabled" : "") + ">" + SVG_ANTERIOR + "</button>";
      numerosDePagina(pagina, totalPaginas).forEach(function (numero) {
        if (numero === "…") {
          html += '<span class="puntos" aria-hidden="true">…</span>';
        } else {
          html += '<button type="button" data-pagina="' + numero + '"'
            + (numero === pagina ? ' aria-current="page"' : "") + ">" + numero + "</button>";
        }
      });
      html += '<button type="button" data-pagina="' + (pagina + 1) + '" aria-label="Página siguiente"'
        + (pagina >= totalPaginas ? " disabled" : "") + ">" + SVG_SIGUIENTE + "</button>";
      nav.innerHTML = html;
    }

    function pintar() {
      var visibles = filas.filter(coincide);
      var total = visibles.length;
      var totalPaginas = Math.max(1, Math.ceil(total / porPagina));
      if (pagina > totalPaginas) pagina = totalPaginas;
      var desde = (pagina - 1) * porPagina;
      filas.forEach(function (fila) { fila.hidden = true; });
      visibles.slice(desde, desde + porPagina).forEach(function (fila) { fila.hidden = false; });

      if (total) {
        if (filaSinResultados.parentNode) filaSinResultados.remove();
      } else if (!filaSinResultados.parentNode) {
        cuerpo.appendChild(filaSinResultados);
      }

      var resumen = contenedor.querySelector("[data-tabla-resumen]");
      if (resumen) {
        resumen.textContent = total
          ? "Mostrando " + (desde + 1) + " – " + Math.min(desde + porPagina, total) + " de " + total + " " + unidad
            + (total < filas.length ? " (de " + filas.length + ")" : "")
          : "Sin resultados";
      }
      pintarPaginas(totalPaginas);
    }

    function ordenar(encabezado, direccion) {
      var indice = encabezado.cellIndex;
      var tipo = encabezado.getAttribute("data-orden");
      filas.sort(function (a, b) {
        var va = valorCelda(a.cells[indice]);
        var vb = valorCelda(b.cells[indice]);
        var resultado = tipo === "numero"
          ? (parseFloat(va) || 0) - (parseFloat(vb) || 0)
          : va.localeCompare(vb, "es", { numeric: true, sensitivity: "base" });
        return direccion === "asc" ? resultado : -resultado;
      });
      filas.forEach(function (fila) { cuerpo.appendChild(fila); });
      if (filaSinResultados.parentNode) cuerpo.appendChild(filaSinResultados);
      tabla.querySelectorAll("th[data-orden]").forEach(function (otro) { otro.removeAttribute("aria-sort"); });
      encabezado.setAttribute("aria-sort", direccion === "asc" ? "ascending" : "descending");
    }

    if (!filas.length) return;

    controles.forEach(function (control) {
      var reiniciar = function () { pagina = 1; pintar(); };
      control.addEventListener("input", reiniciar);
      control.addEventListener("change", reiniciar);
    });

    if (selectorTamano) {
      selectorTamano.addEventListener("change", function () {
        porPagina = parseInt(selectorTamano.value, 10) || 10;
        pagina = 1;
        pintar();
      });
    }

    contenedor.addEventListener("click", function (evento) {
      var botonPagina = evento.target.closest("[data-pagina]");
      if (botonPagina && !botonPagina.disabled) {
        pagina = parseInt(botonPagina.getAttribute("data-pagina"), 10) || 1;
        pintar();
        return;
      }
      var botonOrden = evento.target.closest("th[data-orden] .orden");
      if (botonOrden) {
        var encabezado = botonOrden.closest("th");
        var actual = encabezado.getAttribute("aria-sort");
        var direccion = actual === "ascending" ? "desc"
          : actual === "descending" ? "asc"
          : (encabezado.getAttribute("data-orden") === "fecha" ? "desc" : "asc");
        ordenar(encabezado, direccion);
        pagina = 1;
        pintar();
      }
    });

    var inicial = tabla.querySelector("th[data-orden-inicial]");
    if (inicial) ordenar(inicial, inicial.getAttribute("data-orden-inicial") === "asc" ? "asc" : "desc");
    pintar();
  }

  document.querySelectorAll("[data-tabla]").forEach(iniciarTabla);

  // Funciones disponibles para el JS propio de cada pagina.
  window.AutoPrizma = { toast: toast, copiar: copiarTexto, cerrarMenus: cerrarMenus };
})();
