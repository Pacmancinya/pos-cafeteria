"""Comprobante de venta y cierre de caja, para imprimir.

Sale como una página angosta (58/80 mm) para el navegador o como texto al
driver de Windows. Ambas salidas leen el mismo comprobante ya guardado.

⚠️ Esto NO es una boleta. Mientras no esté conectada la facturación electrónica,
el comprobante lo dice en grande: si pareciera una boleta sin serlo, el local
quedaría expuesto. Ver docs/CONTRATO.md sección 5.
"""
from __future__ import annotations
from html import escape, unescape
import re
from typing import Literal
from apps.pos import local as datos_local
from apps.pos import impresion_windows, sesion

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from apps.pos.api.turnos import (_conteo, _cuadre_de_medios, _efectivo_esperado,
                                 _ingresos_del_turno, _propinas, _retiros_dict,
                                 _retiros_del_turno)
from apps.pos.db.models import Turno, Venta
from apps.pos.db.session import get_session
from core.config import (DENOMINACIONES, MEDIOS_PAGO, NOMBRE_LOCAL, NOMBRE_MEDIO,
                         a_local, modo_demo, neto_iva)

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


def _pagina(titulo: str, cuerpo: str, papel: int = 80) -> HTMLResponse:
    if papel not in (58, 80):
        raise HTTPException(422, "El papel debe ser de 58 u 80 mm.")
    plantilla = PLANTILLA.replace("size:80mm", f"size:{papel}mm").replace(
        "width:72mm", f"width:{papel - 8}mm")
    return HTMLResponse(plantilla.replace("__TITULO__", titulo).replace("__CUERPO__", cuerpo))


def _plata(n: int) -> str:
    return "$" + f"{int(n):,}".replace(",", ".")


def _cabecera_del_local() -> str:
    """El nombre del local y, si están, su RUT y su dirección. Desde la 2.19
    salen de la base: antes el papel decía «Kofe» en cualquier local."""
    from html import escape
    d = datos_local.datos()
    extra = "".join(f'<div class="chico">{escape(x)}</div>'
                    for x in (f"RUT {d['rut']}" if d["rut"] else "", d["direccion"]) if x)
    return f'<div class="local">{escape(d["nombre"])}</div>{extra}'


@router.get("/comprobante/{venta_id}")
def comprobante(venta_id: int, s: Session = Depends(get_session), papel: int = 80):
    titulo, cuerpo = _comprobante(venta_id, s)
    return _pagina(titulo, cuerpo, papel)


def _comprobante(venta_id: int, s: Session) -> tuple[str, str]:
    v = s.get(Venta, venta_id)
    if not v:
        raise HTTPException(404, "No existe esa venta")
    f = a_local(v.creada_at)
    cobrado = v.total - v.descuento
    neto, iva = neto_iva(cobrado)

    filas = "".join(
        f"<tr><td>{l.cantidad} x {escape(l.nombre)}{escape(' ' + l.detalle) if l.detalle else ''}</td>"
        f"<td class='num'>{_plata(l.subtotal)}</td></tr>"
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

    # Un pago mixto dice cuánto fue en cada forma. «Mixto» a secas no sirve para
    # revisar después contra la máquina del banco.
    if v.medio_pago == "mixto":
        from apps.pos.api.turnos import _pagos_de
        filas_pago = "".join(
            f"<tr><td>Pago {NOMBRE_MEDIO.get(m, m)}</td><td class='num'>{_plata(mt)}</td></tr>"
            for m, mt in _pagos_de(s, v))
    else:
        filas_pago = (f"<tr><td>Pago</td><td class='num'>"
                      f"{NOMBRE_MEDIO.get(v.medio_pago, v.medio_pago)}</td></tr>")

    cuerpo = f"""
    <div class="centro">
      {_cabecera_del_local()}
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
      {filas_pago}
      <tr class="chico"><td>Neto</td><td class="num">{_plata(neto)}</td></tr>
      <tr class="chico"><td>IVA 19%</td><td class="num">{_plata(iva)}</td></tr>
    </table>
    {anulada}
    <div class="aviso">NO ES BOLETA<br>Comprobante interno del local</div>
    {'<div class="aviso">DEMO · datos de ejemplo</div>' if modo_demo() else ''}
    <div class="centro chico" style="margin-top:9px">¡Gracias!</div>"""
    return f"Comprobante {v.numero}", cuerpo


class ImpresionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    impresora: str = Field(min_length=1, max_length=256)
    papel: Literal[58, 80] = 80


def _lineas(cuerpo: str) -> list[str]:
    """Texto de nuestra plantilla fija, NO un conversor de HTML arbitrario.

    html.parser no viene en los motores Kofe ya instalados. Usamos solamente
    módulos presentes en ellos para que la actualización no exija reinstalar.
    Los datos están escapados por _comprobante; se decodifican DESPUÉS de
    separar las etiquetas, de modo que <script> escrito en un producto es texto.
    """
    partes = []
    for token in re.findall(r"<[^>]*>|[^<]+", cuerpo):
        if not token.startswith("<"):
            partes.append(" ".join(unescape(token).split()))
        elif re.match(r"</?(?:div|tr|br)\b", token):
            partes.append("\n")
        elif token == "</td>":
            partes.append("  ")
    return [linea.strip() for linea in "".join(partes).splitlines() if linea.strip()]


def _bloques_comprobante(venta_id: int, s: Session) -> list:
    """El comprobante para la impresora de tickets, en bloques con su forma.

    Sale de los MISMOS datos que el comprobante del navegador (la venta guardada),
    pero dibujado para papel angosto: el nombre del local grande y centrado, una
    raya entre secciones, los importes pegados a la derecha y el TOTAL en doble
    alto. Antes se convertía el HTML a texto plano y el papel salía como una lista
    de renglones pegados a la izquierda.
    """
    v = s.get(Venta, venta_id)
    if not v:
        raise HTTPException(404, "No existe esa venta")
    f = a_local(v.creada_at)
    cobrado = v.total - v.descuento
    neto, iva = neto_iva(cobrado)
    d = datos_local.datos()

    bloques: list = [{"tipo": "titulo", "texto": d["nombre"]}]
    for extra in (f"RUT {d['rut']}" if d["rut"] else "", d["direccion"]):
        if extra:
            bloques.append({"tipo": "centro", "texto": extra})
    bloques += [
        {"tipo": "centro", "texto": f"Comprobante interno N {v.numero}"},
        {"tipo": "centro", "texto": f.strftime("%d-%m-%Y  %H:%M")},
        {"tipo": "separador"},
    ]
    for l in v.lineas:
        nombre = f"{l.cantidad} x {l.nombre}" + (f" {l.detalle}" if l.detalle else "")
        bloques.append({"tipo": "cols", "izq": nombre, "der": _plata(l.subtotal)})
        if l.cantidad > 1:
            bloques.append({"tipo": "chico", "texto": f"   {_plata(l.precio_unitario)} c/u"})
    bloques.append({"tipo": "separador"})
    if v.descuento:
        bloques.append({"tipo": "cols", "izq": "Subtotal", "der": _plata(v.total)})
        bloques.append({"tipo": "cols", "izq": "Descuento", "der": "-" + _plata(v.descuento)})
    bloques.append({"tipo": "total", "izq": "TOTAL", "der": _plata(cobrado)})
    if v.propina:
        bloques.append({"tipo": "cols", "izq": "Propina", "der": _plata(v.propina)})
    if v.medio_pago == "mixto":
        from apps.pos.api.turnos import _pagos_de
        for m, mt in _pagos_de(s, v):
            bloques.append({"tipo": "cols", "izq": f"Pago {NOMBRE_MEDIO.get(m, m)}",
                            "der": _plata(mt)})
    else:
        bloques.append({"tipo": "cols", "izq": "Pago",
                        "der": NOMBRE_MEDIO.get(v.medio_pago, v.medio_pago)})
    bloques.append({"tipo": "chico", "texto": f"Neto {_plata(neto)}   IVA 19% {_plata(iva)}"})
    if v.estado == "anulada":
        bloques += [{"tipo": "separador"}, {"tipo": "aviso", "texto": "VENTA ANULADA"}]
    bloques += [
        {"tipo": "separador"},
        {"tipo": "aviso", "texto": "NO ES BOLETA"},
        {"tipo": "chico", "texto": "Comprobante interno del local", "centrado": True},
    ]
    if modo_demo():
        bloques.append({"tipo": "aviso", "texto": "DEMO - DATOS DE EJEMPLO"})
    bloques += [
        {"tipo": "blanco"},
        {"tipo": "centro", "texto": "¡Gracias!"},
    ]
    return bloques


def _enviar(datos: ImpresionIn, lineas: list, crudo: bool = False):
    try:
        enviar = impresion_windows.imprimir_crudo if crudo else impresion_windows.imprimir
        return enviar(datos.impresora, datos.papel, lineas)
    except impresion_windows.ErrorImpresion as e:
        raise HTTPException(e.estado, str(e)) from e


@router.get("/api/v1/impresion/impresoras")
def impresoras(quien: dict = Depends(sesion.exige("config"))):
    try:
        return impresion_windows.listar()
    except impresion_windows.ErrorImpresion as e:
        raise HTTPException(e.estado, str(e)) from e


@router.post("/api/v1/impresion/prueba")
def prueba_impresion(datos: ImpresionIn, quien: dict = Depends(sesion.exige("config"))):
    return _prueba(datos)


@router.post("/api/v1/impresion/crudo/prueba")
def prueba_cruda(datos: ImpresionIn, quien: dict = Depends(sesion.exige("config"))):
    return _prueba(datos, crudo=True)


def _prueba(datos: ImpresionIn, crudo: bool = False):
    if crudo:
        # Se ve igual que un comprobante de verdad: es la forma de revisar el
        # papel, el corte y las tildes antes de cobrarle a alguien.
        return _enviar(datos, [
            {"tipo": "titulo", "texto": datos_local.nombre()},
            {"tipo": "centro", "texto": "PRUEBA DE IMPRESIÓN"},
            {"tipo": "centro", "texto": f"Papel de {datos.papel} mm"},
            {"tipo": "separador"},
            {"tipo": "cols", "izq": "2 x Café chico", "der": "$2.400"},
            {"tipo": "chico", "texto": "   $1.200 c/u"},
            {"tipo": "cols", "izq": "1 x Marraqueta ñ", "der": "$1.190"},
            {"tipo": "separador"},
            {"tipo": "total", "izq": "TOTAL", "der": "$3.590"},
            {"tipo": "cols", "izq": "Pago", "der": "Efectivo"},
            {"tipo": "separador"},
            {"tipo": "aviso", "texto": "NO ES BOLETA"},
            {"tipo": "chico", "texto": "Prueba sin venta ni cobro.", "centrado": True},
        ], crudo=True)
    return _enviar(datos, [datos_local.nombre(), "PRUEBA DE IMPRESIÓN",
                          f"Papel de {datos.papel} mm", "Café · azúcar · ñ · $1.234",
                          "NO ES BOLETA", "Prueba sin venta ni cobro."], crudo=crudo)


@router.post("/api/v1/impresion/comprobante/{venta_id}")
def imprimir_comprobante(venta_id: int, datos: ImpresionIn,
                         s: Session = Depends(get_session),
                         quien: dict = Depends(sesion.exige("vender"))):
    return _imprimir_comprobante(venta_id, datos, s)


@router.post("/api/v1/impresion/crudo/comprobante/{venta_id}")
def imprimir_comprobante_crudo(venta_id: int, datos: ImpresionIn,
                               s: Session = Depends(get_session),
                               quien: dict = Depends(sesion.exige("vender"))):
    return _imprimir_comprobante(venta_id, datos, s, crudo=True)


def _imprimir_comprobante(venta_id: int, datos: ImpresionIn, s: Session, crudo: bool = False):
    # Ruta síncrona: FastAPI la atiende fuera del event loop. Termina la lectura
    # antes de esperar al driver, para no retener una transacción de SQLite.
    if crudo:
        # La térmica recibe el comprobante dibujado para papel angosto; la
        # impresora normal sigue recibiendo el mismo texto que el navegador.
        lineas = _bloques_comprobante(venta_id, s)
    else:
        _, cuerpo = _comprobante(venta_id, s)
        lineas = _lineas(cuerpo)
    s.rollback()
    return _enviar(datos, lineas, crudo=crudo)


class InstalacionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    puerto: str = Field(min_length=1, max_length=256)
    nombre: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9 ._()-]+$")


@router.get("/api/v1/impresion/puertos")
def puertos_impresion(quien: dict = Depends(sesion.exige("config"))):
    try:
        return impresion_windows.puertos_sin_impresora()
    except impresion_windows.ErrorImpresion as e:
        raise HTTPException(e.estado, str(e)) from e


@router.post("/api/v1/impresion/instalar")
def instalar_impresora(datos: InstalacionIn, quien: dict = Depends(sesion.exige("config"))):
    try:
        return impresion_windows.instalar(datos.puerto, datos.nombre)
    except impresion_windows.ErrorImpresion as e:
        raise HTTPException(e.estado, str(e)) from e


@router.get("/cierre/{turno_id}")
def cierre(turno_id: int, s: Session = Depends(get_session), papel: int = 80):
    """El papelito del cierre de caja: lo que se pega en el cuaderno."""
    t = s.get(Turno, turno_id)
    if not t:
        raise HTTPException(404, "No existe ese turno")

    ventas = s.exec(select(Venta).where(Venta.turno_id == t.id, Venta.estado == "pagada")).all()
    anuladas = s.exec(select(Venta).where(Venta.turno_id == t.id, Venta.estado == "anulada")).all()

    por_medio = {m: [0, 0] for m in MEDIOS_PAGO}
    total = propinas = descuentos = 0
    from apps.pos.api.turnos import _pagos_de
    for v in ventas:
        cobrado = v.total - v.descuento
        # Por partes, con el mismo criterio que el cierre en pantalla. Antes se
        # hacía por_medio[v.medio_pago], y desde que existe el pago mixto ese
        # campo puede valer "mixto", que no es una de las claves: el papel del
        # cierre de CUALQUIER turno con una venta mixta se caía con un error y
        # no se podía imprimir. Es el mismo tropiezo que tuvo El día (2.15).
        for medio, monto in _pagos_de(s, v):
            if medio in por_medio:
                por_medio[medio][0] += 1
                por_medio[medio][1] += monto
        total += cobrado
        descuentos += v.descuento
        propinas += v.propina
    neto, iva = neto_iva(total)
    # La misma fórmula que la pantalla: fondo + efectivo − propinas pagadas −
    # retiros del turno. Antes acá se sumaba sin restar nada, así que el papel
    # decía un esperado distinto al de la caja cuando había propinas pagadas.
    esperado = _efectivo_esperado(s, t)

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

    # La plata que se movió a mano en el turno: retiros (salió, para comprar) e
    # ingresos (entró, cambio que se repuso). Cada uno con su motivo y su firma:
    # es lo que hace que el efectivo esperado de arriba sea creíble y no un número
    # que apareció distinto sin explicación.
    bloque_retiros_turno = ""
    movs = [r for r in _retiros_dict(s, t) if not r["anulado"]]
    if movs:
        def _fila(r):
            signo = "+" if r["tipo"] == "ingreso" else "-"
            return (f"<tr><td>{r['hora']} {r['motivo']} ({r['hecho_por'] or '—'})</td>"
                    f"<td class='num'>{signo}{_plata(r['monto'])}</td></tr>")
        filas_r = "".join(_fila(r) for r in movs)
        neto = _ingresos_del_turno(s, t) - _retiros_del_turno(s, t)
        signo = "+" if neto >= 0 else "-"
        bloque_retiros_turno = (
            "<div class='raya'></div>"
            "<div class='chico centro'>PLATA MOVIDA EN EL TURNO</div>"
            "<table>" + filas_r +
            f"<tr class='total'><td>Neto</td>"
            f"<td class='num'>{signo}{_plata(abs(neto))}</td></tr></table>")

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
      {_cabecera_del_local()}
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
    {bloque_retiros_turno}
    {bloque_tarjetas}
    {bloque_propinas}
    {bloque_retiro}
    {f"<div class='chico' style='margin-top:8px'>Nota: {t.nota}</div>" if t.nota else ""}
    <div class="raya"></div>
    <table class="chico">
      <tr><td>Firma cajero</td><td class="num">_______________</td></tr>
    </table>"""
    return _pagina(f"Cierre de caja {abre.strftime('%d-%m-%Y')}", cuerpo, papel)
