/* Cuentas y búsquedas compartidas por la lista, la ficha y los movimientos. */
(function (raiz) {
  "use strict";
  const normalizar = (s) => String(s ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
  const redondear = (n, paso = 10) => Math.ceil(Math.max(0, n) / paso) * paso;
  const ganancia = (costo, venta) => costo > 0 ? (venta / costo - 1) * 100 : null;
  const venta = (costo, porcentaje) => Math.round(costo * (1 + porcentaje / 100));
  const costo = (precio, porcentaje) => porcentaje > -100 ? Math.round(precio / (1 + porcentaje / 100)) : 0;
  const sugerido = (c, margen, paso) => margen >= 0 && margen < 100 ? redondear(c / (1 - margen / 100), paso) : 0;
  const codigo = (s) => /^\d{12}$/.test(String(s).trim()) ? "0" + String(s).trim() : String(s).trim();
  const plu = (s) => String(s ?? "").replace(/^0+/, "") || "0";
  const exacto = (p, q) => (p.codigos || []).some((b) => codigo(b.codigo) === codigo(q));
  const coincide = (p, q) => !normalizar(q) || normalizar(p.nombre).includes(normalizar(q))
    || (p.codigos || []).some((b) => b.codigo.includes(String(q).trim()))
    || (!!p.plu && (normalizar(p.plu).includes(normalizar(q)) || (/^\d+$/.test(q) && plu(p.plu) === plu(q))));
  const porComprar = (p) => p.cuenta && p.minimo > 0 && p.stock < p.minimo;
  const api = { normalizar, redondear, ganancia, venta, costo, sugerido, codigo, exacto, coincide, porComprar };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else raiz.InventarioLogica = api;
})(typeof window !== "undefined" ? window : globalThis);
