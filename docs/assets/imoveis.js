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
      Array.prototype.forEach.call(tab.tBodies[0].rows, function (tr) {
        tr.hidden = q && semAcento(tr.cells[0].textContent).indexOf(q) < 0;
      });
    });
  });

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
