"""El escáner: de un número de código de barras a un producto.

## La consulta más caliente de la caja

En una botillería, "dame el producto de este código" pasa una vez por cada
artículo vendido, con la fila esperando. Por eso `codigobarra.codigo` es la
llave primaria y hay índice por `producto_id`: la búsqueda es directa, no un
recorrido de la tabla.

## Por qué un producto puede tener varios códigos

Porque la lata suelta y el pack de 6 traen códigos distintos y son el mismo
trago. El `cuantos` de cada código dice cuántas unidades entrega: 1 la lata, 6
el pack. Así el pack descuenta seis del mismo saldo sin ninguna tabla extra.

## De dónde sale el nombre cuando el código es desconocido

De Open Food Facts, que es libre de verdad (ODbL, sin clave). Y hay que ser
honesto sobre cuánto sirve: tiene 6.680 productos chilenos contra 4,7 millones
en el mundo. Para un almacén —leche, bebidas, abarrotes de marca— acierta harto.
Para una botillería no: es una base NUTRICIONAL, la gente escanea yogur y no una
caja de cerveza. Ahí no hay ninguna base gratis que sirva.

Por eso esto es un ATAJO PARA ESCRIBIR EL NOMBRE, nunca el catálogo. El precio
no está en ninguna base del mundo: ese es del local. Y si Open Food Facts no
contesta, no pasa nada: se escribe el nombre a mano, que es lo que se hacía
igual.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from apps.pos import sesion
from apps.pos.db.models import CodigoBarra, Producto
from apps.pos.db.session import get_session
from core.codigos import es_de_balanza, es_una_caja, normalizar, por_que_no_sirve
from core.schemas import CodigoIn

router = APIRouter(prefix="/api/v1", tags=["códigos"])

# Open Food Facts pide un User-Agent que diga quién llama, y su regla es "una
# consulta = un escaneo de verdad". Acá se cumple sola: solo se pregunta por un
# código que la caja no conoce, y apenas se guarda el producto no se vuelve a
# preguntar nunca.
AGENTE = "Kofe-POS/1.0 (punto de venta de barrio; rupitohr@gmail.com)"
URL_OFF = "https://world.openfoodfacts.org/api/v2/product/{}.json"

# Corto a propósito: esto pasa con el cliente esperando. Si no contesta rápido,
# se escribe el nombre a mano y listo.
ESPERA = 4


def buscar_por_codigo(s: Session, codigo: str) -> Producto | None:
    fila = s.get(CodigoBarra, codigo)
    if not fila:
        return None
    return s.get(Producto, fila.producto_id)


@router.get("/codigos/{codigo}")
def leer(codigo: str, s: Session = Depends(get_session),
         quien: dict = Depends(sesion.exige("vender"))):
    """Qué producto es este código. Es lo que llama la caja al escanear."""
    limpio = normalizar(codigo)
    problema = por_que_no_sirve(codigo)

    if limpio:
        fila = s.get(CodigoBarra, limpio)
        if fila:
            p = s.get(Producto, fila.producto_id)
            if p and p.activo:
                return {"encontrado": True, "codigo": limpio, "cuantos": fila.cuantos,
                        "producto": {"id": p.id, "nombre": p.nombre, "precio": p.precio,
                                     "categoria_id": p.categoria_id}}
            if p:
                return {"encontrado": False, "codigo": limpio,
                        "problema": f"«{p.nombre}» está guardado pero sacado de la venta. "
                                    "Actívalo en la pestaña Carta."}

    return {
        "encontrado": False,
        "codigo": limpio,
        # Se puede guardar como producto nuevo solo si el código sirve para
        # identificar algo. Un código de balanza NO: cambia con cada trozo.
        "se_puede_guardar": bool(limpio) and not problema,
        "problema": problema,
        "de_balanza": es_de_balanza(codigo),
        "es_una_caja": es_una_caja(codigo),
    }


@router.get("/codigos/{codigo}/sugerir")
def sugerir(codigo: str, quien: dict = Depends(sesion.exige("editar_carta"))):
    """Cómo se llama este producto, según Open Food Facts.

    Nunca lanza: que no haya internet, o que el producto no esté, no puede
    impedir crearlo a mano. Devuelve el nombre vacío y ya.
    """
    limpio = normalizar(codigo)
    if not limpio:
        return {"nombre": "", "marca": "", "de_donde": ""}

    pedido = urllib.request.Request(
        URL_OFF.format(limpio) + "?fields=product_name,product_name_es,brands,quantity",
        headers={"User-Agent": AGENTE})
    try:
        with urllib.request.urlopen(pedido, timeout=ESPERA) as r:
            datos = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return {"nombre": "", "marca": "", "de_donde": ""}

    if datos.get("status") != 1:
        return {"nombre": "", "marca": "", "de_donde": ""}

    p = datos.get("product") or {}
    nombre = (p.get("product_name_es") or p.get("product_name") or "").strip()
    marca = (p.get("brands") or "").split(",")[0].strip()
    cuanto = (p.get("quantity") or "").strip()

    return {"nombre": _como_lo_escribiria_una_persona(nombre, marca, cuanto),
            "marca": marca,
            "de_donde": "Open Food Facts" if nombre or marca else ""}


def _como_lo_escribiria_una_persona(nombre: str, marca: str, cuanto: str) -> str:
    """Junta marca, nombre y contenido como se escriben en una carta.

    Open Food Facts los guarda por separado, y sueltos no sirven:

        nombre "Tradición", marca "Nescafé"   -> "Nescafé Tradición 170g"
        nombre "Leche Entera", marca "Colun"  -> "Colun Leche Entera 1 l"
        nombre "Coca-Cola", marca "Coca-Cola" -> "Coca-Cola 350 ml"

    La marca va ADELANTE y no es un adorno: "Tradición" sola no le dice nada a
    nadie parado frente a la caja. Y no se repite cuando ya está en el nombre,
    que es el caso de las marcas que se llaman igual que su producto.
    """
    dentro = nombre.lower()
    partes = []
    if marca and marca.lower() not in dentro:
        partes.append(marca)
    if nombre:
        partes.append(nombre)
    if cuanto and cuanto.lower().replace(" ", "") not in dentro.replace(" ", ""):
        partes.append(cuanto)
    return " ".join(partes).strip()


@router.post("/productos/{producto_id}/codigos")
def pegar(producto_id: int, datos: CodigoIn, s: Session = Depends(get_session),
          quien: dict = Depends(sesion.exige("editar_carta"))):
    """Le pega un código a un producto que ya existe."""
    p = s.get(Producto, producto_id)
    if not p:
        raise HTTPException(404, "No existe ese producto")

    limpio = normalizar(datos.codigo)
    problema = por_que_no_sirve(datos.codigo)
    if problema:
        raise HTTPException(422, problema)

    ya = s.get(CodigoBarra, limpio)
    if ya and ya.producto_id != producto_id:
        otro = s.get(Producto, ya.producto_id)
        raise HTTPException(409, f"Ese código ya es de «{otro.nombre if otro else '?'}». "
                            "Un código de barras identifica un producto y solo uno.")

    if ya:
        ya.cuantos = max(1, datos.cuantos)
        ya.nota = datos.nota
        s.add(ya)
    else:
        s.add(CodigoBarra(codigo=limpio, producto_id=producto_id,
                          cuantos=max(1, datos.cuantos), nota=datos.nota))
    s.commit()
    return {"ok": True, "codigo": limpio}


@router.get("/productos/{producto_id}/codigos")
def listar(producto_id: int, s: Session = Depends(get_session),
           quien: dict = Depends(sesion.exige("vender"))):
    filas = s.exec(select(CodigoBarra).where(CodigoBarra.producto_id == producto_id)).all()
    return [{"codigo": f.codigo, "cuantos": f.cuantos, "nota": f.nota} for f in filas]


@router.delete("/codigos/{codigo}")
def despegar(codigo: str, s: Session = Depends(get_session),
             quien: dict = Depends(sesion.exige("editar_carta"))):
    fila = s.get(CodigoBarra, normalizar(codigo) or codigo)
    if not fila:
        raise HTTPException(404, "Ese código no está guardado")
    s.delete(fila)
    s.commit()
    return {"ok": True}
