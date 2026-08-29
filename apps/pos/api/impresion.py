"""Comprobante de venta y cierre de caja, para imprimir.

Sale como una página angosta (80 mm) que se manda a imprimir con el navegador.
Así funciona con la impresora térmica del local **y** con cualquier impresora
normal, sin depender de drivers ni de ESC/POS.

⚠️ Esto NO es una boleta. Mientras no esté conectada la facturación electrónica,
el comprobante lo dice en grande: si pareciera una boleta sin serlo, el local
quedaría expuesto. Ver docs/CONTRATO.md sección 5.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select

from apps.pos.api.turnos import (_conteo, _cuadre_de_medios, _efectivo_del_turno,
                                 _propinas)
from apps.pos.db.models import Turno, Venta
from apps.pos.db.session import get_session
from core.config import (DENOMINACIONES, MEDIOS_PAGO, NOMBRE_LOCAL, NOMBRE_MEDIO,
                         a_local, neto_iva)

router = APIRouter(tags=["impresión"])


def _quien(s, usuario_id) -> str:
    """El nombre de un usuario, aunque lo hayan sacado de la caja.

    A propósito NO filtra por `activo`: el papel de un cierre de marzo tiene que
    seguir diciendo quién lo firmó, aunque esa persona ya no trabaje ahí.
    """
    if not usuario_id:
        return ""
    from apps.pos.db.models import Usuario
    u = s.get(Usuario, usuario_id)
    return u.nombre if u else ""

PLANTILLA = """<!doctype html>
<html lang="es-CL"><head><meta charset="utf-8">
<title>__TITULO__</title>
<style>
  @page{ size:80mm auto; margin:4mm }
  *{box-sizing:border-box;margin:0;padding:0}
  body{
    width:72mm;margin:0 auto;padding:6px 0 18px;
    font-family:"Consolas","Courier New",monospace;font-size:12px;line-height:1.45;color:#000;
    background:#fff;
  }
  .centro{text-align:center}
  .local{font-size:17px;font-weight:700;letter-spacing:.06em}
  .chico{font-size:10.5px}
  .raya{border-top:1px dashed #000;margin:7px 0}
  table{width:100%;border-collapse:collapse}
  td{vertical-align:top;padding:1px 0}
  .num{text-align:right;white-space:nowrap}
  .total{font-size:16px;font-weight:700}
  .aviso{
    border:1.5px solid #000;padding:5px 6px;margin-top:10px;text-align:center;
    font-size:10.5px;font-weight:700;letter-spacing:.03em;
  }
  .noimprimir{margin-top:16px;text-align:center}
  .noimprimir button{
    font:inherit;font-size:13px;padding:9px 16px;border:1px solid #000;
    background:#fff;border-radius:6px;cursor:pointer;
  }
  @media print{ .noimprimir{display:none} }
</style></head>
<body>
__CUERPO__
<div class="noimprimir">
  <button onclick="window.print()">Imprimir</button>
  <button onclick="window.close()">Cerrar</button>
</div>
<script>window.addEventListener("load", () => setTimeout(() => window.print(), 350));</script>
</body></html>"""


def _pagina(titulo: str, cuerpo: str) -> HTMLResponse:
    return HTMLResponse(PLANTILLA.replace("__TITULO__", titulo).replace("__CUERPO__", cuerpo))


def _plata(n: int) -> str:
    return "$" + f"{int(n):,}".replace(",", ".")


@router.get("/comprobante/{venta_id}")
def comprobante(venta_id: int, s: Session = Depends(get_session)):
    v = s.get(Venta, venta_id)
    if not v:
        raise HTTPException(404, "No existe esa venta")
    f = a_local(v.creada_at)
    cobrado = v.total - v.descuento
    neto, iva = neto_iva(cobrado)

    filas = "".join(
        f"<tr><td>{l.cantidad} x {l.nombre}</td><td class='num'>{_plata(l.subtotal)}</td></tr>"
        f"<tr><td class='chico' colspan='2'>&nbsp;&nbsp;&nbsp;{_plata(l.precio_unitario)} c/u</td></tr>"
        for l in v.lineas
    )
    anulada = ("<div class='aviso'>VENTA ANULADA</div>" if v.estado == "anulada" else "")
    propina = (f"<tr><td>Propina</td><td class='num'>{_plata(v.propina)}</td></tr>"
               if v.propina else "")
    descuento = ""
    if v.descuento:
        descuento = (f"<tr><td>Subtotal</td><td class='num'>{_plata(v.total)}</td></tr>"
                     f"<tr><td>Descuento</td><td class='num'>-{_plata(v.descuento)}</td></tr>")

    cuerpo = f"""
    <div class="centro">
      <div class="local">{NOMBRE_LOCAL}</div>
      <div class="chico">Comprobante interno N° {v.numero}</div>
      <div class="chico">{f.strftime('%d-%m-%Y  %H:%M')}</div>
    </div>
    <div class="raya"></div>
    <table>{filas}</table>
    <div class="raya"></div>
    <table>
      {descuento}
      <tr class="total"><td>TOTAL</td><td class="num">{_plata(cobrado)}</td></tr>
      {propina}
      <tr><td>Pago</td><td class="num">{NOMBRE_MEDIO.get(v.medio_pago, v.medio_pago)}</td></tr>
      <tr class="chico"><td>Neto</td><td class="num">{_plata(neto)}</td></tr>
      <tr class="chico"><td>IVA 19%</td><td class="num">{_plata(iva)}</td></tr>
    </table>
    {anulada}
    <div class="aviso">NO ES BOLETA<br>Comprobante interno del local</div>
    <div class="centro chico" style="margin-top:9px">¡Gracias!</div>"""
    return _pagina(f"Comprobante {v.numero}", cuerpo)


@router.get("/cierre/{turno_id}")
def cierre(turno_id: int, s: Session = Depends(get_session)):
    """El papelito del cierre de caja: lo que se pega en el cuaderno."""
    t = s.get(Turno, turno_id)
    if not t:
        raise HTTPException(404, "No existe ese turno")

    ventas = s.exec(select(Venta).where(Venta.turno_id == t.id, Venta.estado == "pagada")).all()
    anuladas = s.exec(select(Venta).where(Venta.turno_id == t.id, Venta.estado == "anulada")).all()

    por_medio = {m: [0, 0] for m in MEDIOS_PAGO}
    total = propinas = descuentos = 0
    for v in ventas:
        cobrado = v.total - v.descuento
        por_medio[v.medio_pago][0] += 1
        por_medio[v.medio_pago][1] += cobrado
        total += cobrado
        descuentos += v.descuento
        propinas += v.propina
    neto, iva = neto_iva(total)
    esperado = t.monto_inicial + _efectivo_del_turno(s, t)

    filas_medio = "".join(
        f"<tr><td>{NOMBRE_MEDIO.get(m, m)} ({c})</td><td class='num'>{_plata(mt)}</td></tr>"
        for m, (c, mt) in por_medio.items() if c
    )
    dif = t.diferencia
    linea_dif = ""
    if dif is not None:
        etiqueta = "CUADRA" if dif == 0 else ("SOBRA" if dif > 0 else "FALTA")
        linea_dif = (f"<tr class='total'><td>{etiqueta}</td>"
                     f"<td class='num'>{_plata(abs(dif))}</td></tr>")

    # El detalle del arqueo: cuántos billetes de cada uno se contaron. Es lo
    # que permite después buscar DÓNDE estuvo el error, no solo cuánto faltó.
    conteo = _conteo(t.conteo_cierre)
    bloque_conteo = ""
    if conteo:
        filas = ""
        for v in DENOMINACIONES:
            n = int(conteo.get(str(v), 0) or 0)
            if n:
                filas += ("<tr><td>" + _plata(v) + " x " + str(n) + "</td>"
                          "<td class='num'>" + _plata(v * n) + "</td></tr>")
        if filas:
            bloque_conteo = ("<div class='raya'></div>"
                             "<div class='chico centro'>ARQUEO DEL CAJON</div>"
                             "<table>" + filas + "</table>")

    # El cuadre de lo que NO es efectivo: lo que dice el POS contra lo que dijo
    # la máquina del banco. Sin esto, el papel del cierre solo prueba el cajón.
    bloque_tarjetas = ""
    filas_t = ""
    for m in _cuadre_de_medios(s, t):
        filas_t += (f"<tr><td>{m['nombre']} ({m['cantidad']})</td>"
                    f"<td class='num'>{_plata(m['esperado'])}</td></tr>")
        if m["declarado"] is not None:
            etiqueta = ("cuadra" if m["diferencia"] == 0
                        else ("sobra " + _plata(m["diferencia"])) if m["diferencia"] > 0
                        else ("falta " + _plata(abs(m["diferencia"]))))
            filas_t += (f"<tr><td class='chico'>segun el banco · {etiqueta}</td>"
                        f"<td class='num chico'>{_plata(m['declarado'])}</td></tr>")
    if filas_t:
        bloque_tarjetas = ("<div class='raya'></div>"
                           "<div class='chico centro'>TARJETAS Y TRANSFERENCIAS</div>"
                           "<table>" + filas_t + "</table>")

    # Las propinas, separadas: la de efectivo ya está en el cajón; la de tarjeta
    # la depositó el banco y hay que pagarla aparte.
    prop = _propinas(s, t)
    bloque_propinas = ""
    if prop["total"]:
        bloque_propinas = (
            "<div class='raya'></div>"
            "<div class='chico centro'>PROPINAS</div><table>"
            f"<tr><td>En efectivo</td><td class='num'>{_plata(prop['efectivo'])}</td></tr>"
            f"<tr><td>Por tarjeta</td><td class='num'>{_plata(prop['tarjeta'])}</td></tr>"
            f"<tr class='total'><td>Total</td><td class='num'>{_plata(prop['total'])}</td></tr>"
            "</table>")

    # Lo que se lleva y lo que queda para mañana.
    bloque_retiro = ""
    if t.fondo_siguiente or t.retiro:
        bloque_retiro = ("<div class='raya'></div><table>"
                         "<tr><td>Queda de fondo</td><td class='num'>" + _plata(t.fondo_siguiente) + "</td></tr>"
                         "<tr><td>Se retira</td><td class='num'>" + _plata(t.retiro) + "</td></tr>"
                         "</table>")

    abre = a_local(t.abierto_at)
    cierra = a_local(t.cerrado_at) if t.cerrado_at else None

    # Quién abrió y quién cerró, con NOMBRE. Normalmente es la misma persona
    # —la caja la cierra quien la abrió— y por eso se imprime en una sola línea.
    # Cuando NO lo es, es porque el dueño pasó por encima de la regla, y esa
    # excepción tiene que verse en el papel que se pega en el cuaderno: si solo
    # vive en la base, en el mostrador no existe.
    quien_abrio = _quien(s, t.abierto_por_id) or t.cajero
    quien_cerro = _quien(s, t.cerrado_por_id)
    otro_cerro = bool(quien_cerro and quien_abrio and quien_cerro != quien_abrio)
    cuerpo = f"""
    <div class="centro">
      <div class="local">{NOMBRE_LOCAL}</div>
      <div class="chico">CIERRE DE CAJA</div>
      <div class="chico">{abre.strftime('%d-%m-%Y')}</div>
    </div>
    <div class="raya"></div>
    <table>
      <tr><td>Cajero</td><td class="num">{t.cajero or '—'}</td></tr>
      <tr><td>Abrió</td><td class="num">{abre.strftime('%H:%M')}</td></tr>
      <tr><td>Cerró</td><td class="num">{cierra.strftime('%H:%M') if cierra else '—'}</td></tr>
      <tr><td>Ventas</td><td class="num">{len(ventas)}</td></tr>
      {f'<tr><td>La abrió</td><td class="num">{quien_abrio}</td></tr>' if quien_abrio else ''}
      {f'<tr><td><b>La cerró</b></td><td class="num"><b>{quien_cerro}</b></td></tr>' if otro_cerro else ''}
    </table>
    <div class="raya"></div>
    <table>{filas_medio}
      <tr class="total"><td>TOTAL</td><td class="num">{_plata(total)}</td></tr>
      <tr class="chico"><td>Neto</td><td class="num">{_plata(neto)}</td></tr>
      <tr class="chico"><td>IVA 19%</td><td class="num">{_plata(iva)}</td></tr>
      {f"<tr><td>Descuentos</td><td class='num'>-{_plata(descuentos)}</td></tr>" if descuentos else ""}
      {f"<tr><td>Propinas</td><td class='num'>{_plata(propinas)}</td></tr>" if propinas else ""}
      {f"<tr class='chico'><td>Anuladas</td><td class='num'>{len(anuladas)}</td></tr>" if anuladas else ""}
    </table>
    {bloque_conteo}
    <div class="raya"></div>
    <table>
      <tr><td>Fondo inicial</td><td class="num">{_plata(t.monto_inicial)}</td></tr>
      <tr><td>Efectivo esperado</td><td class="num">{_plata(esperado)}</td></tr>
      <tr><td>Efectivo contado</td><td class="num">{_plata(t.efectivo_contado or 0)}</td></tr>
      {linea_dif}
    </table>
    {bloque_tarjetas}
    {bloque_propinas}
    {bloque_retiro}
    {f"<div class='chico' style='margin-top:8px'>Nota: {t.nota}</div>" if t.nota else ""}
    <div class="raya"></div>
    <table class="chico">
      <tr><td>Firma cajero</td><td class="num">_______________</td></tr>
    </table>"""
    return _pagina(f"Cierre de caja {abre.strftime('%d-%m-%Y')}", cuerpo)
