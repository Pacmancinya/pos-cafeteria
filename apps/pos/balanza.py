"""La etiqueta propone un peso o un total; el servidor decide si se puede cobrar.

Escanear y vender usan esta misma cuenta. La consulta de la pantalla es solo una
vista previa: entre ella y el cobro pueden cambiar el precio, el formato o el
estado del ticket. Nunca se acepta un precio calculado por el navegador.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlmodel import Session, select

from apps.pos.api import ajustes
from apps.pos.db.models import CodigoBarra, Producto, Venta, VentaLinea
from core.codigos import es_de_balanza, leer_balanza, limpiar
from core.config import a_local, ahora


def plu_normalizado(plu: str) -> str:
    """Los ceros del relleno no forman parte del número, pero vacío no es PLU 0."""
    return (plu.lstrip("0") or "0") if plu else ""


@dataclass
class CobroBalanza:
    codigo: str
    modo: str
    nombre: str = "Balanza"
    detalle: str = ""
    precio: int = 0
    producto_id: int | None = None
    repetible: bool = False
    peso_g: int = 0
    problema: str = ""

    def para_caja(self) -> dict:
        return {k: getattr(self, k) for k in (
            "codigo", "modo", "nombre", "detalle", "precio", "producto_id", "repetible")}


def resolver(s: Session, codigo: str) -> CobroBalanza | None:
    """None si el local no usa balanza o si el código no es una etiqueta.

    El ajuste se revisa ACÁ y no en la pantalla, porque escanear y cobrar pasan
    los dos por esta función: una pantalla vieja o un pedido armado a mano no
    pueden cobrar una etiqueta en un local que no la prendió.
    """
    preferencias = ajustes._leer(s)
    if not preferencias["usar_balanza"]:
        return None
    limpio = limpiar(codigo)
    if s.get(CodigoBarra, limpio):
        # Un código que ya es de un producto de la carta nunca se lee como etiqueta,
        # ni al escanear (que lo busca antes) ni en un pedido armado a mano.
        return None
    if preferencias.get("formato_balanza_roto"):
        if not es_de_balanza(limpio):
            return None
        return CobroBalanza(codigo=limpio, modo="", problema=(
            "El formato de la balanza guardado no se entiende, así que no se cobran "
            "etiquetas. Revísalo y guárdalo de nuevo en Ayuda → Ajustes."))
    lectura = leer_balanza(codigo, preferencias["formato_balanza"])
    if lectura is None:
        return None
    cobro = CobroBalanza(codigo=limpiar(codigo), modo=lectura["modo"])
    if cobro.modo == "ticket":
        ticket = lectura["ticket"]
        cobro.detalle = f"Ticket {ticket}"
        cobro.precio = lectura["total"]
        # El código ENTERO identifica el papel. El número de ticket solo se
        # recicla en la balanza; por eso tampoco se reserva para siempre.
        venta = s.exec(select(Venta).join(VentaLinea).where(
            VentaLinea.codigo_balanza == cobro.codigo,
            VentaLinea.modo_balanza == "ticket",
            Venta.estado == "pagada",
            Venta.creada_at >= ahora() - timedelta(hours=24),
        ).order_by(Venta.creada_at.desc())).first()
        if venta:
            hora = a_local(venta.creada_at).strftime("%H:%M")
            cobro.problema = (
                f"El ticket {ticket} de la balanza ya se cobró a las {hora}, "
                f"en la venta {venta.numero}. Si hay que cobrarlo de nuevo, "
                "anula esa venta primero.")
            return cobro
    else:
        plu = plu_normalizado(lectura["plu"])
        productos = [p for p in s.exec(select(Producto).where(
            Producto.activo == True, Producto.plu != "")).all()  # noqa: E712
            if plu_normalizado(p.plu) == plu]
        if not productos:
            cobro.problema = (f"La balanza mandó el PLU {plu} y ningún producto de la carta "
                              "lo tiene. Pónselo en la ficha del producto.")
            return cobro
        if len(productos) > 1:
            # Una base antigua puede traer duplicados anteriores a la validación.
            # Elegir el primero cobraría un precio al azar.
            cobro.problema = (f"El PLU {plu} está en más de un producto. "
                              "Déjalo en una sola ficha antes de cobrar.")
            return cobro
        p = productos[0]
        cobro.producto_id, cobro.nombre, cobro.repetible = p.id, p.nombre, True
        if cobro.modo == "plu_precio":
            cobro.precio, cobro.detalle = lectura["total"], f"PLU {plu}"
        else:
            peso = lectura["peso_kg"]
            if peso <= 0:
                cobro.problema = "La etiqueta de la balanza trae peso 0. Vuelve a pesar el producto."
                return cobro
            if p.precio_kilo <= 0:
                cobro.problema = (f"«{p.nombre}» no tiene precio por kilo. "
                                  "Pónselo en la ficha del producto antes de cobrar.")
                return cobro
            cobro.precio = int((Decimal(p.precio_kilo) * peso).to_integral_value(
                rounding=ROUND_HALF_UP))
            # Si una balanza usa fracciones de gramo, el cobro conserva el peso
            # original; solo la copia en gramos y el texto se redondean.
            cobro.peso_g = int((peso * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            kilos = format(peso.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP), ".3f")
            precio_kilo = f"{p.precio_kilo:,}".replace(",", ".")
            cobro.detalle = f"{kilos.replace('.', ',')} kg a ${precio_kilo}/kg"
    if cobro.precio <= 0:
        cobro.problema = "La etiqueta de la balanza da un total de $0. Vuelve a pesar el producto."
    elif cobro.precio > 99_000_000:
        cobro.problema = ("La etiqueta de la balanza supera $99.000.000. "
                          "Revisa el formato y el precio antes de cobrar.")
    return cobro
