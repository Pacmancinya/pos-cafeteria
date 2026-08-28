"""Traer la carta que el local ya tiene.

Un cliente nuevo llega con su lista de productos en un Excel, en un CSV, o
simplemente copiada de un Word. Escribir cuarenta productos a mano es la razón
más tonta por la que alguien no empieza a usar el sistema.

**Nunca se importa a ciegas.** Son dos pasos separados a propósito: primero se
lee el archivo y se devuelve lo que se entendió, y recién cuando la persona lo
miró y lo confirmó se escribe en la base. El archivo del cliente siempre trae
algo raro —un total al final, una fila de encabezado, un producto repetido— y
lo único que evita que eso entre a la caja es que alguien lo vea antes.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from apps.pos import sesion
from apps.pos.db.models import Categoria, Producto
from apps.pos.db.session import get_session
from core import planilla
from core.schemas import AplicarImportacionIn, TextoImportadoIn

router = APIRouter(prefix="/api/v1/importar", tags=["importar"])

# Un archivo de carta no pesa más que esto. El tope existe para que nadie
# cuelgue la caja subiendo un video por equivocación.
TOPE_BYTES = 8 * 1024 * 1024


def _existentes(s: Session) -> dict[str, Producto]:
    """Lo que ya está en la carta, por nombre normalizado."""
    productos = s.exec(select(Producto)).all()
    return {planilla.sin_tildes(p.nombre): p for p in productos}


def _comparar(s: Session, leidos: list[dict]) -> dict:
    """Qué pasaría con cada producto del archivo si se aplicara."""
    ya = _existentes(s)
    filas = []
    nuevos = actualizados = iguales = 0
    for p in leidos:
        anterior = ya.get(planilla.sin_tildes(p["nombre"]))
        if anterior is None:
            que_pasa, precio_anterior = "nuevo", None
            nuevos += 1
        elif anterior.precio != p["precio"]:
            que_pasa, precio_anterior = "cambia_precio", anterior.precio
            actualizados += 1
        else:
            que_pasa, precio_anterior = "igual", anterior.precio
            iguales += 1
        filas.append({**p, "que_pasa": que_pasa, "precio_anterior": precio_anterior})

    # Lo que está en la caja y NO viene en el archivo. Solo se informa: sacarlo
    # es una decisión aparte, porque un archivo incompleto no puede borrar la
    # carta del local.
    en_archivo = {planilla.sin_tildes(p["nombre"]) for p in leidos}
    sobran = [p.nombre for clave, p in ya.items() if clave not in en_archivo and p.activo]

    return {
        "productos": filas,
        "resumen": {"nuevos": nuevos, "cambian_precio": actualizados,
                    "iguales": iguales, "total": len(filas)},
        "no_estan_en_el_archivo": sorted(sobran)[:50],
        "categorias": sorted({p["categoria"] for p in leidos}),
    }


def _previsualizar(s: Session, filas: list[list[str]]) -> dict:
    if not filas:
        raise HTTPException(422, "No pude leer nada del archivo. ¿Es un Excel o un CSV?")
    leido = planilla.interpretar(filas)
    if not leido["productos"]:
        raise HTTPException(
            422, "Leí el archivo pero no encontré productos con nombre. "
                 "Revisa que tenga una columna con el nombre y otra con el precio.")
    return {**_comparar(s, leido["productos"]),
            "avisos": leido["avisos"],
            "columnas_detectadas": leido["columnas_detectadas"],
            "filas_leidas": len(filas)}


@router.post("/archivo")
async def desde_archivo(archivo: UploadFile = File(...),
                        s: Session = Depends(get_session),
                        quien: dict = Depends(sesion.exige("editar_carta"))):
    datos = await archivo.read()
    if not datos:
        raise HTTPException(422, "El archivo llegó vacío.")
    if len(datos) > TOPE_BYTES:
        raise HTTPException(413, "El archivo es demasiado grande para ser una carta.")
    return {**_previsualizar(s, planilla.leer(archivo.filename or "", datos)),
            "origen": archivo.filename}


@router.post("/texto")
def desde_texto(datos: TextoImportadoIn, s: Session = Depends(get_session),
                quien: dict = Depends(sesion.exige("editar_carta"))):
    """Para pegar la lista directamente, copiada de un Excel o de un Word."""
    return {**_previsualizar(s, planilla.desde_texto(datos.texto)),
            "origen": "lo que pegaste"}


@router.post("/aplicar")
def aplicar(datos: AplicarImportacionIn, s: Session = Depends(get_session),
            quien: dict = Depends(sesion.exige("editar_carta"))):
    """Escribe en la carta lo que la persona confirmó.

    Llega la lista ya revisada —puede haber sacado filas o corregido precios en
    la pantalla—, no el archivo. Lo que no vino en esta lista no se toca.
    """
    if not datos.productos:
        raise HTTPException(422, "No quedó ningún producto para traer.")

    ya = _existentes(s)
    categorias = {planilla.sin_tildes(c.nombre): c
                  for c in s.exec(select(Categoria)).all()}
    creados = actualizados = 0

    for p in datos.productos:
        nombre = (p.nombre or "").strip()
        if not nombre:
            continue

        # La categoría se crea sola si no existe: obligar a crearlas antes
        # convertiría una importación en dos trámites.
        clave_cat = planilla.sin_tildes(p.categoria or "Carta")
        cat = categorias.get(clave_cat)
        if cat is None:
            cat = Categoria(nombre=(p.categoria or "Carta").strip(),
                            orden=len(categorias))
            s.add(cat)
            s.flush()
            categorias[clave_cat] = cat

        anterior = ya.get(planilla.sin_tildes(nombre))
        if anterior is not None:
            # Solo el precio y la vuelta a la venta. El dibujo y la descripción
            # no se pisan: si alguien ya los ajustó a mano, esa decisión vale
            # más que lo que adivinó el importador.
            anterior.precio = p.precio
            anterior.activo = True
            if p.descripcion and not anterior.descripcion:
                anterior.descripcion = p.descripcion
            s.add(anterior)
            actualizados += 1
        else:
            nuevo = Producto(
                categoria_id=cat.id,
                nombre=nombre[:80],
                descripcion=(p.descripcion or "")[:120],
                precio=max(0, p.precio),
                dibujo=p.dibujo or "mug",
                orden=creados,
            )
            s.add(nuevo)
            creados += 1

    sacados = 0
    if datos.sacar_lo_que_no_vino:
        # Borrado lógico, igual que en el resto del sistema: las ventas viejas
        # tienen que seguir cuadrando.
        vienen = {planilla.sin_tildes(p.nombre) for p in datos.productos}
        for clave, viejo in ya.items():
            if clave not in vienen and viejo.activo:
                viejo.activo = False
                s.add(viejo)
                sacados += 1

    s.commit()
    return {
        "ok": True,
        "creados": creados,
        "actualizados": actualizados,
        "sacados": sacados,
        "aviso": _contar(creados, actualizados, sacados),
    }


def _contar(creados: int, actualizados: int, sacados: int) -> str:
    partes = []
    if creados:
        partes.append(f"{creados} producto{'s' if creados != 1 else ''} nuevo"
                      f"{'s' if creados != 1 else ''}")
    if actualizados:
        partes.append(f"{actualizados} con el precio al día")
    if sacados:
        partes.append(f"{sacados} sacado{'s' if sacados != 1 else ''} de la venta")
    return "Listo: " + (", ".join(partes) if partes else "no hubo cambios") + "."
