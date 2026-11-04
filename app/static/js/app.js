// StudiScore Frontend: jQuery (Ajax + DOM), Leaflet (Karte), Chart.js (Radar)

// Deutsche Bezeichnungen für die OSM amenity-Werte (Popup + Liste)
const AMENITY_LABELS = {
  library: "Bibliothek", university: "Universität", college: "Hochschule/Schule",
  cafe: "Café", restaurant: "Restaurant", fast_food: "Fast Food", food_court: "Food Court", ice_cream: "Glace",
  bar: "Bar", pub: "Pub", nightclub: "Club", biergarten: "Biergarten",
  cinema: "Kino", theatre: "Theater", arts_centre: "Kulturzentrum", community_centre: "Gemeinschaftszentrum",
  events_venue: "Eventlokal",
  bicycle_rental: "Veloverleih", bus_station: "Busbahnhof", car_sharing: "Carsharing", ferry_terminal: "Schiffsstation",
  pharmacy: "Apotheke", doctors: "Arztpraxis", atm: "Bankomat", bank: "Bank", post_office: "Post", marketplace: "Markt"
};
const LEVELS = ["nicht wichtig", "mittel", "wichtig"];

let categories = [];      // aus /api/categories
let catByKey = {};
let map, radarChart;
let centerMarker = null, radiusCircle = null;
let layers = {};          // Kategorie -> L.layerGroup
let hidden = {};          // Kategorie -> true, wenn auf der Karte ausgeblendet
let lastResult = null;
let lastPois = [];
let recalcTimer = null;

// ---------- Hilfsfunktionen ----------

function esc(text) {
  return $("<div>").text(text == null ? "" : text).html();
}

function formatDist(m) {
  return m < 1000 ? m + " m" : (m / 1000).toFixed(1) + " km";
}

function setStatus(text, loading) {
  $("#status, #landing-status").text(text || "").toggleClass("loading", !!loading);
}

// kleiner Fortschrittsring (SVG) für den Teilscore
function ring(percent, color) {
  const r = 15, c = 2 * Math.PI * r;
  const filled = (percent / 100) * c;
  return '<svg class="ring" viewBox="0 0 36 36">' +
    '<circle cx="18" cy="18" r="' + r + '" fill="none" stroke="#eceef2" stroke-width="4"/>' +
    '<circle cx="18" cy="18" r="' + r + '" fill="none" stroke="' + color + '" stroke-width="4" stroke-linecap="round"' +
    ' stroke-dasharray="' + filled + ' ' + c + '" transform="rotate(-90 18 18)"/></svg>';
}

function levelBars(level) {
  let html = '<span class="bars">';
  for (let i = 0; i < 3; i++) html += '<i class="' + (i <= level ? "on" : "") + '"></i>';
  return html + "</span>";
}

// ---------- Aufbau: Fragen, Legende, Karte, Chart ----------

function buildQuestions() {
  const box = $("#questions").empty();
  categories.forEach(function (c) {
    let seg = '<div class="segmented">';
    LEVELS.forEach(function (label, i) {
      const id = "w_" + c.key + "_" + i;
      seg += '<input type="radio" form="score-form" name="w_' + c.key + '" id="' + id + '" value="' + i + '"' +
        (i === 1 ? " checked" : "") + '><label for="' + id + '">' + label + "</label>";
    });
    seg += "</div>";
    box.append(
      '<div class="question">' +
      '<span class="q-dot" style="background:' + c.color + '"></span>' +
      '<div class="q-text">' + esc(c.label) + "</div>" +
      seg + "</div>"
    );
  });
}

// Kompakte Prioritäten im Resultat: Klick wechselt nicht wichtig -> mittel -> wichtig
function buildPrioChips() {
  const box = $("#prio-chips").empty();
  box.append('<span class="muted small prio-label">Prioritäten</span>');
  categories.forEach(function (c) {
    box.append('<span class="prio-chip" data-key="' + c.key + '"><i class="dot" style="background:' + c.color +
      '"></i>' + esc(c.label) + ' <span class="lvl"></span></span>');
  });
  updateCompact();
}

function currentLevel(key) {
  return Number($('input[name="w_' + key + '"]:checked').val());
}

// Kompakte Steuerung an die Hauptfelder (Schritt 2) angleichen
function updateCompact() {
  categories.forEach(function (c) {
    const level = currentLevel(c.key);
    const chip = $('.prio-chip[data-key="' + c.key + '"]');
    chip.removeClass("level-0 level-1 level-2").addClass("level-" + level)
      .attr("title", c.label + ": " + LEVELS[level] + " (klicken zum Ändern)");
    chip.find(".lvl").html(levelBars(level));
  });
  const r = $("#radius").val();
  $("#radius-compact").val(r);
  $("#radius-compact-value, #radius-value").text(r + " km");
}

function scheduleRecalc() {
  if (!lastResult) return;
  clearTimeout(recalcTimer);
  recalcTimer = setTimeout(function () { calculate(false); }, 250);
}

function buildLegend() {
  const box = $("#legend").empty();
  categories.forEach(function (c) {
    const chip = $('<span class="chip" data-key="' + c.key + '"><i style="background:' + c.color + '"></i>' + esc(c.label) + "</span>");
    box.append(chip);
  });
  box.on("click", ".chip", function () {
    const key = $(this).data("key");
    hidden[key] = !hidden[key];
    updateLayerVisibility();
  });
}

function initMap() {
  // Karte wie in den Slides (SW 11), Startansicht: ganze Schweiz
  // scrollWheelZoom erst nach Klick in die Karte, sonst zoomt man beim Scrollen der Seite aus Versehen
  map = L.map("map", { preferCanvas: true, scrollWheelZoom: false, zoomControl: false }).setView([46.8, 8.23], 8);
  map.on("click", function () { map.scrollWheelZoom.enable(); });
  map.on("mouseout", function () { map.scrollWheelZoom.disable(); });
  L.control.zoom({ position: "bottomright" }).addTo(map);
  // OSM-Tiles wie in den Slides; minimalistisch gemacht per CSS-Filter (.leaflet-tile-pane)
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
  }).addTo(map);
  categories.forEach(function (c) {
    layers[c.key] = L.layerGroup().addTo(map);
  });
}

function initChart() {
  const ctx = document.getElementById("radar").getContext("2d");
  radarChart = new Chart(ctx, {
    type: "radar",
    data: {
      labels: categories.map(function (c) { return c.label; }),
      datasets: [{
        label: "Teilscore",
        data: categories.map(function () { return 0; }),
        backgroundColor: "rgba(47, 158, 68, 0.18)",
        borderColor: "rgba(47, 158, 68, 1)",
        pointBackgroundColor: categories.map(function (c) { return c.color; }),
        pointRadius: 5,
        borderWidth: 2
      }, {
        label: "Deine Priorität",
        data: categories.map(function () { return 50; }),
        backgroundColor: "rgba(22, 23, 29, 0.03)",
        borderColor: "rgba(22, 23, 29, 0.55)",
        borderDash: [5, 5],
        pointRadius: 0,
        borderWidth: 1.5
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        r: {
          min: 0, max: 100,
          ticks: { stepSize: 25, display: false },
          pointLabels: { font: { size: 13, family: "Inter" } }
        }
      },
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, font: { family: "Inter" } } },
        tooltip: {
          callbacks: {
            label: function (item) {
              if (item.datasetIndex === 1) return "Priorität: " + LEVELS[[25, 50, 100].indexOf(item.raw)];
              return "Teilscore: " + item.raw;
            }
          }
        }
      }
    }
  });
}

// ---------- PLZ-Suche ----------

function suggest(q) {
  $.getJSON("/api/search", { q: q }, function (json) {
    const list = $("#plz-suggestions").empty();
    json.results.forEach(function (r) {
      list.append('<option value="' + r.plz + " " + esc(r.name) + '">' + r.canton + "</option>");
    });
  });
}

// Eingabe -> PLZ. "8400 Winterthur" oder "8400" direkt, sonst Ortsname suchen.
function resolvePlz(text, callback) {
  const m = text.match(/\b\d{4}\b/);
  if (m) return callback(m[0]);
  $.getJSON("/api/search", { q: text }, function (json) {
    if (json.results.length) {
      $("#plz-input, #landing-input").val(json.results[0].plz + " " + json.results[0].name);
      callback(json.results[0].plz);
    } else {
      setStatus("Kein Ort gefunden: " + text);
    }
  });
}

// ---------- Score berechnen (POST wie SW 10) ----------

// Dashboard beim ersten Resultat einblenden und hinscrollen
function scrollToEl(selector) {
  $("html, body").animate({ scrollTop: $(selector).offset().top - 24 }, 700);
}

// Schritt 1 -> 2: PLZ prüfen, dann Prioritäten-Seite einblenden
function goToPrefs() {
  const text = $.trim($("#landing-input").val());
  if (!text) {
    setStatus("Bitte PLZ eingeben");
    return;
  }
  resolvePlz(text, function (plz) {
    $.getJSON("/api/plz/" + plz)
      .done(function (loc) {
        setStatus("");
        $("#plz").val(plz);
        $("#plz-input, #landing-input").val(loc.plz + " " + loc.name);
        $("#prefs-place").text(loc.plz + " " + loc.name + " (" + loc.canton + ")");
        $("#prefs").removeClass("hidden");
        scrollToEl("#prefs");
      })
      .fail(function (xhr) {
        setStatus(xhr.responseJSON && xhr.responseJSON.error ? xhr.responseJSON.error : "Server nicht erreichbar");
      });
  });
}

// Schritt 3: Resultat einblenden (beim ersten Mal Karte/Chart neu ausmessen)
function showDashboard(scroll) {
  if ($("#dashboard").hasClass("hidden")) {
    $("#dashboard").removeClass("hidden");
    map.invalidateSize();
    radarChart.resize();
  }
  if (scroll) scrollToEl("#dashboard");
}

function calculate(scroll) {
  const text = $.trim($("#plz-input").val());
  if (!text) {
    setStatus("Bitte PLZ eingeben");
    return;
  }
  resolvePlz(text, function (plz) {
    $("#plz").val(plz);
    setStatus("Berechne …", true);
    $.post("/api/score", $("#score-form").serialize())
      .done(function (data) {
        setStatus("");
        lastResult = data;
        showDashboard(scroll);
        renderScore(data);
        loadPois(data);
      })
      .fail(function (xhr) {
        const msg = xhr.responseJSON && xhr.responseJSON.error ? xhr.responseJSON.error : "Server nicht erreichbar";
        setStatus(msg);
      });
  });
}

function renderScore(data) {
  const loc = data.location;
  $("#score-value").text(data.score);
  $("#score-caption").html("StudiScore für" + '<span class="place">' + loc.plz + " " + esc(loc.name) +
    ' <span class="canton">' + loc.canton + "</span></span>");
  $("#prefs-place").text(loc.plz + " " + loc.name + " (" + loc.canton + ")");

  // Verlaufsbalken: Verlauf über ganze Breite, sichtbar bis zum Score
  const barWidth = $(".bar").width();
  $("#bar-fill").css({ width: data.score + "%", "background-size": barWidth + "px 100%" });
  $("#bar-label").text(data.score >= 8 ? data.score : "");
  if (data.percentile !== null) {
    $("#percentile-text").html('<span class="accent">' + data.percentile + " %</span> der Schweizer PLZ liegen tiefer");
  }

  // KPIs
  const cats = data.categories.slice().sort(function (a, b) { return b.subscore - a.subscore; });
  const best = cats[0], worst = cats[cats.length - 1];
  $("#kpi-total").text(data.total_pois.toLocaleString("de-CH"));
  $("#kpi-total-note").text("auf " + data.area_km2 + " km² (r = " + data.radius + " km)");
  $("#kpi-best").text(best.label);
  $("#kpi-best-note").text("Teilscore " + Math.round(best.subscore));
  if (Math.round(worst.subscore) === Math.round(best.subscore)) {
    $("#kpi-worst").text("keine");
    $("#kpi-worst-note").text("alle Teilscores " + Math.round(worst.subscore));
  } else {
    $("#kpi-worst").text(worst.label);
    $("#kpi-worst-note").text("Teilscore " + Math.round(worst.subscore));
  }

  // Radar-Chart aktualisieren
  radarChart.data.datasets[0].data = data.categories.map(function (c) { return c.subscore; });
  radarChart.data.datasets[1].data = data.categories.map(function (c) { return c.weight * 50; });
  radarChart.update();

  // Aufschlüsselung
  const rows = $("#breakdown-rows").empty();
  rows.append('<div class="rows-head"><span class="h-icon"></span><span class="h-name">Kategorie</span>' +
    '<span class="h-prio">Prio</span><span class="h-score">Score</span><span class="h-contrib">Punkte</span></div>');
  data.categories.forEach(function (c) {
    rows.append(
      '<div class="row">' +
      '<div class="row-icon" style="background:' + c.color + '">' + esc(c.label.charAt(0)) + "</div>" +
      '<div class="row-name"><strong>' + esc(c.label) + "</strong><span>" + c.count + " Orte</span></div>" +
      '<div class="row-level">' + levelBars(c.level) + c.level_label + "</div>" +
      '<div class="row-weight">× ' + c.weight + "</div>" +
      ring(c.subscore, c.color) +
      '<div class="row-score">' + Math.round(c.subscore) + "</div>" +
      '<div class="row-contrib"><b>+' + c.contribution.toFixed(1) + "</b> Pkt</div>" +
      "</div>"
    );
  });
  rows.append('<div class="row total"><div class="row-name"><strong>Gesamt-Score</strong>' +
    "<span>gewichteter Mittelwert der Teilscores</span></div>" +
    '<div class="row-contrib"><b>' + data.score + "</b> / 100</div></div>");
}

// ---------- POIs auf der Karte ----------

function loadPois(data) {
  const loc = data.location;
  // Kategorien, die "nicht wichtig" sind, starten ausgeblendet
  data.categories.forEach(function (c) { hidden[c.key] = c.level === 0; });

  $.getJSON("/api/pois", { lat: loc.lat, lon: loc.lon, radius: data.radius }, function (json) {
    lastPois = json.pois;
    categories.forEach(function (c) { layers[c.key].clearLayers(); });

    json.pois.forEach(function (p) {
      const c = catByKey[p.category];
      let popup = "<strong>" + esc(p.name || AMENITY_LABELS[p.amenity]) + "</strong><br>" +
        AMENITY_LABELS[p.amenity] + " · " + c.label + "<br>" + formatDist(p.dist) + " vom Zentrum";
      if (p.street) popup += "<br>" + esc(p.street);
      if (p.opening_hours) popup += "<br>🕑 " + esc(p.opening_hours);
      if (p.website) popup += '<br><a href="' + esc(p.website) + '" target="_blank">Website</a>';
      L.circleMarker([p.lat, p.lon], {
        radius: 6, color: "#fff", weight: 1.5, fillColor: c.color, fillOpacity: 0.9
      })
        .bindTooltip("<strong>" + esc(p.name || AMENITY_LABELS[p.amenity]) + "</strong><br><span>" +
          AMENITY_LABELS[p.amenity] + " · " + formatDist(p.dist) + "</span>",
          { direction: "top", offset: [0, -6], className: "poi-tooltip" })
        .bindPopup(popup)
        .addTo(layers[p.category]);
    });

    if (centerMarker) map.removeLayer(centerMarker);
    if (radiusCircle) map.removeLayer(radiusCircle);
    radiusCircle = L.circle([loc.lat, loc.lon], {
      radius: data.radius * 1000, color: "#16171d", weight: 1, opacity: 0.5, dashArray: "4 6",
      fillColor: "#16171d", fillOpacity: 0.03, interactive: false  // sonst blockiert der Kreis die Tooltips
    }).addTo(map);
    centerMarker = L.marker([loc.lat, loc.lon], {
      icon: L.divIcon({ className: "", html: '<div class="center-marker"></div>', iconSize: [18, 18] })
    }).bindPopup("<strong>" + loc.plz + " " + esc(loc.name) + "</strong><br>Zentrum (" +
      (loc.center_source === "osm" ? "Median der OSM-Orte" : "swisstopo") + ")").addTo(map);
    map.fitBounds(radiusCircle.getBounds(), { padding: [10, 10] });

    updateLayerVisibility();
  });
}

function updateLayerVisibility() {
  categories.forEach(function (c) {
    if (hidden[c.key]) map.removeLayer(layers[c.key]);
    else layers[c.key].addTo(map);
    $('.chip[data-key="' + c.key + '"]').toggleClass("off", !!hidden[c.key]);
  });
  renderNearest();
}

function renderNearest() {
  const list = $("#nearest").empty();
  const visible = lastPois.filter(function (p) { return !hidden[p.category] && p.name; });
  if (!visible.length) {
    list.append('<li class="muted">–</li>');
    return;
  }
  visible.slice(0, 9).forEach(function (p) {
    list.append(
      "<li><i style=\"background:" + catByKey[p.category].color + "\"></i>" +
      '<div class="n-name"><strong>' + esc(p.name) + "</strong><span>" + AMENITY_LABELS[p.amenity] + "</span></div>" +
      '<span class="n-dist">' + formatDist(p.dist) + "</span></li>"
    );
  });
}

// ---------- Start ----------

$(document).ready(function () {
  $.getJSON("/api/categories", function (json) {
    categories = json.categories;
    categories.forEach(function (c) { catByKey[c.key] = c; });
    buildQuestions();
    buildPrioChips();
    buildLegend();
    initMap();
    initChart();
  }).fail(function () {
    setStatus("Server nicht erreichbar");
  });

  $("#score-form").submit(function () {
    calculate(false);
    return false; // kein Reload (SW 10)
  });

  // Schritt 1: grosse PLZ-Eingabe
  $("#landing-form").submit(function () {
    goToPrefs();
    return false;
  });
  $(".example").click(function () {
    $("#landing-input").val($(this).data("plz"));
    goToPrefs();
    return false;
  });

  // Schritt 2 -> 3
  $("#show-result").click(function () {
    calculate(true);
  });

  // Enter sendet ab (auch wenn die Datalist-Vorschläge offen sind)
  $("#plz-input, #landing-input").on("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      $(this).closest("form").submit();
    }
  });

  $("#plz-input, #landing-input").on("input", function () {
    const q = $.trim($(this).val());
    if (q.length >= 2) suggest(q);
  });

  // Hauptfelder (Schritt 2) geändert -> kompakte Anzeige nachziehen (+ neu rechnen, falls schon Resultat)
  $("#radius").on("input", updateCompact);
  $(document).on("change", "#radius, #questions input", function () {
    updateCompact();
    scheduleRecalc();
  });

  // Kompakte Steuerung im Resultat -> Hauptfelder setzen, neu rechnen
  $("#radius-compact").on("input", function () {
    $("#radius").val($(this).val());
    updateCompact();
  }).on("change", scheduleRecalc);
  $("#prio-chips").on("click", ".prio-chip", function () {
    const key = $(this).data("key");
    const next = (currentLevel(key) + 1) % 3;
    $('input[name="w_' + key + '"][value="' + next + '"]').prop("checked", true);
    updateCompact();
    scheduleRecalc();
  });
});
