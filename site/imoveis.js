/* Imóveis em Números: filtro da tabela de bairros e "Compare um imóvel" na curva de preços. */
(function () {
  "use strict";
  function semAcento(s) { return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); }
  function nf(v) { return Math.round(v).toLocaleString("pt-BR"); }
  function num(s) {
    s = String(s || "").replace(/[^\d,\.]/g, "");
    if (s.indexOf(",") >= 0) s = s.replace(/\./g, "").replace(",", ".");
    else if ((s.match(/\./g) || []).length > 1 || /\.\d{3}$/.test(s)) s = s.replace(/\./g, "");
    var v = parseFloat(s);
    return isFinite(v) ? v : null;
  }

  // filtro da tabela
  Array.prototype.forEach.call(document.querySelectorAll("[data-filtro]"), function (inp) {
    var tab = document.getElementById(inp.getAttribute("data-filtro"));
    if (!tab) return;
    inp.addEventListener("input", function () {
      var q = semAcento(inp.value.trim());
      var todos = tab.getAttribute("data-todos") === "1";
      Array.prototype.forEach.call(tab.tBodies[0].rows, function (tr) {
        var col = +(inp.getAttribute("data-col") || 0);
        if (q) tr.hidden = semAcento(tr.cells[col].textContent).indexOf(q) < 0;
        else tr.hidden = !todos && tr.classList.contains("mais");
      });
    });
  });

  // "Mostrar todos os bairros"
  Array.prototype.forEach.call(document.querySelectorAll("[data-mais]"), function (bt) {
    var tab = document.getElementById(bt.getAttribute("data-mais"));
    bt.addEventListener("click", function () {
      tab.setAttribute("data-todos", "1");
      Array.prototype.forEach.call(tab.querySelectorAll("tr.mais"), function (tr) { tr.hidden = false; });
      bt.hidden = true;
    });
  });

  // ranking com pesos escolhidos pela pessoa
  var tab = document.getElementById("tab-rank"), caixa = document.getElementById("pesos");
  if (tab && caixa) {
    var dados = JSON.parse(tab.getAttribute("data-rank")), padrao = JSON.parse(tab.getAttribute("data-pesos"));
    var ins = caixa.querySelectorAll("input[type=range]"), corpo = tab.tBodies[0];
    var bt = document.querySelector('[data-mais="tab-rank"]');
    function refaz() {
      var w = Array.prototype.map.call(ins, function (i) { i.nextElementSibling.textContent = i.value; return +i.value; });
      var parte = +tab.getAttribute("data-parte"), n = w.length - 1;
      var tot = 0; for (var k = 0; k < n; k++) tot += w[k];
      var v = tot ? Math.min(w[n] * parte, 1) : 1;
      var lin = dados.map(function (d) {
        var s = 0; for (var i = 0; i < n; i++) s += w[i] * d[3][i];
        var estr = tot ? s / tot : 0;
        return [d, ((1 - v) * estr + v * d[3][n]) * 100];
      }).sort(function (a, b) { return b[1] - a[1]; });
      var todos = tab.getAttribute("data-todos") === "1", html = "";
      lin.forEach(function (x, i) {
        var d = x[0], esc = function (s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;"); };
        html += '<tr' + (i >= 30 && !todos ? ' class="mais" hidden' : (i >= 30 ? ' class="mais"' : '')) + '><td class="num">' + (i + 1) +
          '</td><td><a href="' + d[1] + '">' + esc(d[0]) + '</a></td><td class="r num"><b>' + nf(x[1]) +
          '</b></td>' + (d.length > 4 ? '<td class="r num">R$ ' + nf(d[4]) + '</td><td class="r num m-esc">R$ ' : '<td class="r num">R$ ') + nf(d[2]) + '</td></tr>';
      });
      corpo.innerHTML = html;
      var f = document.querySelector('[data-filtro="tab-rank"]');
      if (f && f.value) f.dispatchEvent(new Event("input"));
    }
    Array.prototype.forEach.call(ins, function (i) { i.addEventListener("input", refaz); });
    document.getElementById("pesos-reset").addEventListener("click", function () {
      Array.prototype.forEach.call(ins, function (i, n) { i.value = padrao[n]; });
      refaz();
    });
  }

  // posição aproximada de um valor na distribuição, pelos quantis 10/25/50/75/90
  function percentil(q, v) {
    var pts = [[0.10, q[0]], [0.25, q[1]], [0.50, q[2]], [0.75, q[3]], [0.90, q[4]]];
    if (v <= pts[0][1]) return Math.max(0.02, 0.10 * v / pts[0][1]);
    for (var i = 1; i < pts.length; i++) {
      if (v <= pts[i][1]) {
        var a = pts[i - 1], b = pts[i];
        return a[0] + (b[0] - a[0]) * (v - a[1]) / ((b[1] - a[1]) || 1);
      }
    }
    return Math.min(0.98, 0.90 + 0.08 * (v - pts[4][1]) / (pts[4][1] - pts[3][1] || 1));
  }

  Array.prototype.forEach.call(document.querySelectorAll("[data-comp]"), function (box) {
    var d = JSON.parse(box.getAttribute("data-comp"));
    var res = box.parentNode.querySelector(".comp-res");
    var preco = box.querySelector("[name=preco]"), area = box.querySelector("[name=area]");
    function calc() {
      var p = num(preco.value), a = num(area.value);
      if (!p || !a || a < 10) { res.textContent = "Digite o preço e a área de um imóvel anunciado para ver em que ponto da curva ele cai."; return; }
      var m2 = p / a, pc = percentil(d.q, m2);
      var txt;
      if (pc < 0.25) txt = "abaixo da faixa do meio: mais barato que " + Math.round((1 - pc) * 100) + "% das vendas";
      else if (pc > 0.75) txt = "acima da faixa do meio: mais caro que " + Math.round(pc * 100) + "% das vendas";
      else txt = "dentro da faixa do meio, onde ficou metade das vendas";
      var dif = m2 / d.q[2] - 1;
      res.innerHTML = "<b>R$ " + nf(m2) + "/m²</b>: " + txt + " (" + (dif >= 0 ? "+" : "−") + Math.abs(Math.round(dif * 100)) + "% contra a mediana).";
    }
    preco.addEventListener("input", calc);
    area.addEventListener("input", calc);
  });
})();
