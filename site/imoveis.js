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
    var preco = box.querySelector("[name=preco]"), area = box.querySelector("[name=area]"), tipo = box.querySelector("[name=tipo]");
    function calc() {
      var p = num(preco.value), a = num(area.value);
      if (!p || !a || a < 10) { res.textContent = "Digite o preço e a área de um imóvel anunciado para ver em que ponto da curva ele cai."; return; }
      var q = (tipo && tipo.value && d.t && d.t[tipo.value]) || d.q;
      var qual = tipo && tipo.value ? (tipo.value === "apto" ? " dos apartamentos" : " das casas") : "";
      var m2 = p / a, pc = percentil(q, m2);
      var txt;
      if (pc < 0.25) txt = "abaixo da faixa do meio: mais barato que " + Math.round((1 - pc) * 100) + "% das vendas" + qual;
      else if (pc > 0.75) txt = "acima da faixa do meio: mais caro que " + Math.round(pc * 100) + "% das vendas" + qual;
      else txt = "dentro da faixa do meio, onde ficou metade das vendas" + qual;
      var dif = m2 / q[2] - 1;
      res.innerHTML = "<b>R$ " + nf(m2) + "/m²</b>: " + txt + " (" + (dif >= 0 ? "+" : "−") + Math.abs(Math.round(dif * 100)) + "% contra a mediana).";
    }
    preco.addEventListener("input", calc);
    area.addEventListener("input", calc);
    if (tipo) tipo.addEventListener("change", calc);
  });

  // abas (Todos / Apartamentos / Casas)
  Array.prototype.forEach.call(document.querySelectorAll(".abas"), function (grupo) {
    var bts = grupo.querySelectorAll("[data-aba]");
    Array.prototype.forEach.call(bts, function (bt) {
      bt.addEventListener("click", function () {
        Array.prototype.forEach.call(bts, function (b) {
          var on = b === bt;
          b.setAttribute("aria-selected", on ? "true" : "false");
          document.getElementById(b.getAttribute("data-aba")).hidden = !on;
        });
      });
    });
  });

  // calculadora de ITBI (mesma conta de itbi_calc no gerador)
  Array.prototype.forEach.call(document.querySelectorAll("[data-itbi]"), function (box) {
    var regras = JSON.parse(box.getAttribute("data-itbi"));
    var cid = box.querySelector("[name=cidade]"), val = box.querySelector("[name=valor]"), fin = box.querySelector("[name=fin]");
    var res = box.querySelector(".itbi-res"), linhaFin = box.querySelector(".itbi-fin");
    function brl(v) { return "R$ " + v.toLocaleString("pt-BR", {minimumFractionDigits: 2, maximumFractionDigits: 2}); }
    function pc(v) { return v.toLocaleString("pt-BR", {maximumFractionDigits: 2}) + "%"; }
    function calc() {
      var r = regras[cid.value], f = r.fin;
      linhaFin.hidden = !f;
      var v = num(val.value), fi = f ? num(fin.value) : 0;
      if (!v) { res.innerHTML = "<p>Digite o valor do imóvel.</p>"; return; }
      var partes = [], imp;
      if (!f || !fi || (f.teto_imovel && v > f.teto_imovel)) {
        imp = v * r.geral / 100;
        partes.push(pc(r.geral) + " sobre " + brl(v));
        if (f && fi && f.teto_imovel && v > f.teto_imovel) partes.push("sem redução: o imóvel passa de " + brl(f.teto_imovel));
      } else {
        var fv = Math.min(fi, v, f.teto_fin || fi);
        imp = fv * f.taxa / 100 + (v - fv) * f.resto / 100;
        partes.push(pc(f.taxa) + " sobre " + brl(fv) + " financiados" + (f.teto_fin && fi > f.teto_fin ? " (limite da redução)" : ""));
        partes.push(pc(f.resto) + " sobre os outros " + brl(v - fv));
      }
      res.innerHTML = "<p class=\"itbi-total\">ITBI: <b>" + brl(imp) + "</b></p><p class=\"small\">" + partes.join("; ") +
        ". Alíquota efetiva: " + pc(imp / v * 100) + ".</p>";
    }
    [cid, val, fin].forEach(function (el) { el.addEventListener(el.tagName === "SELECT" ? "change" : "input", calc); });
    calc();
  });

  // simulador de financiamento (SAC e Price)
  Array.prototype.forEach.call(document.querySelectorAll("[data-fin]"), function (box) {
    var D = JSON.parse(box.getAttribute("data-fin"));
    function el(n) { return box.querySelector("[name=" + n + "]"); }
    var valor = el("valor"), entrada = el("entrada"), prazo = el("prazo"), linha = el("linha"), banco = el("banco"),
        taxa = el("taxa"), cidade = el("cidade"), res = box.querySelector(".fin-res"), outra = box.querySelector(".fin-outra");
    function brl(v) { return "R$ " + Math.round(v).toLocaleString("pt-BR"); }
    function pcs(v) { return v.toLocaleString("pt-BR", {maximumFractionDigits: 2}) + "%"; }
    function bancos() {
      var l = linha.value, ops = '<option value="med">Média dos bancos (' + pcs(D.med[l] || 0) + ' ao ano)</option>';
      (D.b[l] || []).forEach(function (b, i) { ops += '<option value="' + i + '">' + b[0] + " (" + pcs(b[1]) + " ao ano)</option>"; });
      banco.innerHTML = ops + '<option value="outra">Outra taxa</option>';
    }
    function itbi(v, fin) {
      var r = D.itbi[cidade.value]; if (!r) return null;
      var f = r.fin;
      if (!f || !fin || (f.teto_imovel && v > f.teto_imovel)) return v * r.geral / 100;
      var fv = Math.min(fin, v, f.teto_fin || fin);
      return fv * f.taxa / 100 + (v - fv) * f.resto / 100;
    }
    function calc() {
      outra.hidden = banco.value !== "outra";
      var v = num(valor.value);
      if (!v) { res.innerHTML = "<p>Digite o valor do imóvel.</p>"; return; }
      var e = num(entrada.value); if (e === null || e === undefined || isNaN(e) || entrada.value.trim() === "") e = v * 0.2;
      var anos = Math.min(Math.max(num(prazo.value) || 30, 1), 35), n = Math.round(anos * 12);
      var aa = banco.value === "outra" ? num(taxa.value) : (banco.value === "med" ? D.med[linha.value] : D.b[linha.value][+banco.value][1]);
      var P = v - e;
      if (!aa || P <= 0) { res.innerHTML = "<p>Confira a entrada e a taxa.</p>"; return; }
      var i = Math.pow(1 + aa / 100, 1 / 12) - 1;
      var sac1 = P / n + P * i, sacN = P / n * (1 + i), sacJ = i * P * (n + 1) / 2;
      var pmt = P * i / (1 - Math.pow(1 + i, -n)), priceJ = pmt * n - P;
      var it = itbi(v, P);
      res.innerHTML =
        '<div class="fin-cols"><div><h3>SAC</h3><p>1ª parcela <b>' + brl(sac1) + "</b></p><p>última " + brl(sacN) + "</p><p>juros no total " + brl(sacJ) +
        "</p><p>renda mínima " + brl(sac1 / 0.3) + "</p></div>" +
        "<div><h3>Price</h3><p>parcela fixa <b>" + brl(pmt) + "</b></p><p>&nbsp;</p><p>juros no total " + brl(priceJ) +
        "</p><p>renda mínima " + brl(pmt / 0.3) + "</p></div></div>" +
        '<p class="fin-mao">Para comprar, você precisa ter <b>' + brl(e + (it || 0)) + "</b>: entrada de " + brl(e) +
        (it !== null ? " + ITBI de " + brl(it) : " (mais o ITBI da sua cidade)") + ".</p>" +
        '<p class="small">Financiando ' + brl(P) + " em " + anos + " anos a " + pcs(aa) + " ao ano.</p>";
    }
    var q = new URLSearchParams(location.search);
    if (q.get("valor")) valor.value = (+q.get("valor")).toLocaleString("pt-BR");
    if (q.get("cidade") && D.itbi[q.get("cidade")]) cidade.value = q.get("cidade");
    bancos();
    linha.addEventListener("change", function () { bancos(); calc(); });
    [valor, entrada, prazo, taxa].forEach(function (x) { x.addEventListener("input", calc); });
    [banco, cidade].forEach(function (x) { x.addEventListener("change", calc); });
    calc();
  });
})();
