"""La carta: categorías y productos.

Incluye `GET /api/v1/carta`, que es lo que leen las pantallas del local.
Ese endpoint es la razón por la que el punto de venta es el dueño de los precios:
una sola lista, no dos.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session, select

from apps.pos.db.models import Categoria, Producto
from apps.pos import sesion
from apps.pos.db.session import get_session
from core.config import AVISOS, NOMBRE_LOCAL
from core.schemas import CategoriaIn, ProductoIn

router = APIRouter(prefix="/api/v1", tags=["carta"])


def _productos_de(s: Session, cat_id: int, solo_activos: bool = True):
    q = select(Producto).where(Producto.categoria_id == cat_id)
    if solo_activos:
        q = q.where(Producto.activo == True)  # noqa: E712
    return s.exec(q.order_by(Producto.orden, Producto.id)).all()


@router.get("/carta")
def carta(respuesta: Response, s: Session = Depends(get_session)):
    """Formato exacto que esperan las pantallas de `menu-cafeteria`.

    CORS abierto a propósito: sin esto el navegador de la pantalla rechaza la
    respuesta y el menú se queda con la carta vieja. Es de solo lectura y solo
    expone precios que ya están a la vista del público.
    """
    respuesta.headers["Access-Control-Allow-Origin"] = "*"
    respuesta.headers["Cache-Control"] = "no-store"

    cats = s.exec(
        select(Categoria).where(Categoria.activa == True).order_by(Categoria.orden, Categoria.id)  # noqa: E712
    ).all()

    salida = []
    for c in cats:
        prods = _productos_de(s, c.id)
        if not prods:
            continue  # una categoría vacía rompe la pantalla; mejor no mandarla
        destacado = next((p for p in prods if p.destacado), None)
        normales = [p for p in prods if not p.destacado] or prods

        def _p(p: Producto) -> dict:
            return {
                "nombre": p.nombre,
                "descripcion": p.descripcion,
                "precio": p.precio,
                "antes": p.antes,
                "etiqueta": p.etiqueta or None,
                "dibujo": p.dibujo,
                "color": p.color or None,
            }

        bloque = {"nombre": c.nombre, "productos": [_p(p) for p in normales]}
        if destacado:
            bloque["destacado"] = {
                **_p(destacado),
                "etiqueta": destacado.badge or "Recomendado de hoy",
            }
        salida.append(bloque)

    return {"local": NOMBRE_LOCAL, "avisos": AVISOS, "categorias": salida}


@router.get("/categorias")
def listar_categorias(s: Session = Depends(get_session)):
    cats = s.exec(select(Categoria).order_by(Categoria.orden, Categoria.id)).all()
    return [
        {
            "id": c.id, "nombre": c.nombre, "orden": c.orden, "activa": c.activa,
            "productos": [
                {
                    "id": p.id, "nombre": p.nombre, "descripcion": p.descripcion,
                    "precio": p.precio, "activo": p.activo, "orden": p.orden,
                    "destacado": p.destacado, "badge": p.badge, "antes": p.antes,
                    "etiqueta": p.etiqueta, "dibujo": p.dibujo, "color": p.color,
                }
                for p in _productos_de(s, c.id, solo_activos=False)
            ],
        }
        for c in cats
    ]


@router.post("/categorias")
def crear_categoria(datos: CategoriaIn, s: Session = Depends(get_session),
                    quien: dict = Depends(sesion.exige("editar_carta"))):
    c = Categoria(**datos.model_dump())
    s.add(c)
    s.commit()
    s.refresh(c)
    return c


@router.put("/categorias/{cat_id}")
def editar_categoria(cat_id: int, datos: CategoriaIn, s: Session = Depends(get_session),
                     quien: dict = Depends(sesion.exige("editar_carta"))):
    c = s.get(Categoria, cat_id)
    if not c:
        raise HTTPException(404, "No existe esa categoría")
    for k, v in datos.model_dump().items():
        setattr(c, k, v)
    s.add(c)
    s.commit()
    s.refresh(c)
    return c


@router.post("/productos")
def crear_producto(datos: ProductoIn, s: Session = Depends(get_session),
                   quien: dict = Depends(sesion.exige("editar_carta"))):
    if not s.get(Categoria, datos.categoria_id):
        raise HTTPException(404, "No existe esa categoría")
    p = Producto(**datos.model_dump())
    _un_solo_destacado(s, p)
    s.add(p)
    s.commit()
    s.refresh(p)
    return p


@router.put("/productos/{prod_id}")
def editar_producto(prod_id: int, datos: ProductoIn, s: Session = Depends(get_session),
                    quien: dict = Depends(sesion.exige("editar_carta"))):
    p = s.get(Producto, prod_id)
    if not p:
        raise HTTPException(404, "No existe ese producto")
    for k, v in datos.model_dump().items():
        setattr(p, k, v)
    _un_solo_destacado(s, p)
    s.add(p)
    s.commit()
    s.refresh(p)
    return p


@router.delete("/productos/{prod_id}")
def borrar_producto(prod_id: int, s: Session = Depends(get_session),
                    quien: dict = Depends(sesion.exige("editar_carta"))):
    """Borrado lógico: las ventas viejas tienen que seguir cuadrando."""
    p = s.get(Producto, prod_id)
    if not p:
        raise HTTPException(404, "No existe ese producto")
    p.activo = False
    s.add(p)
    s.commit()
    return {"ok": True, "id": prod_id, "activo": False}


def _un_solo_destacado(s: Session, p: Producto) -> None:
    """La pantalla tiene un solo recuadro grande por categoría: si marcas otro,
    el anterior se desmarca solo. Evita el 'por qué no se ve mi destacado'."""
    if not p.destacado:
        return
    otros = s.exec(
        select(Producto).where(
            Producto.categoria_id == p.categoria_id,
            Producto.destacado == True,  # noqa: E712
        )
    ).all()
    for o in otros:
        if o.id != p.id:
            o.destacado = False
            s.add(o)
