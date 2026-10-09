"""Config → Pantallas del local: los televisores con nombre y lo que dicen las pantallas.

Dos puertas distintas, a propósito:

  · `GET /api/v1/pantallas/config` es PÚBLICA, como la carta: los televisores no tienen teclado
    para un PIN (ver acceso.LIBRES). Solo lee, y solo devuelve textos de la carta y ajustes de
    pantalla que ya están a la vista de cualquiera que mire el televisor.
  · Todo lo que cambia algo vive en `/api/v1/config/…` y pide el PIN de Config.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from apps.pos import pantallas
from apps.pos.api import config as puerta_config

router = APIRouter(prefix="/api/v1", tags=["pantallas"])


class TiemposIn(BaseModel):
    vitrina: int = Field(ge=pantallas.MIN_SEG, le=pantallas.MAX_SEG)
    cat: int = Field(ge=pantallas.MIN_SEG, le=pantallas.MAX_SEG)
    reco: int = Field(ge=pantallas.MIN_SEG, le=pantallas.MAX_SEG)


class TelevisorIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=30)
    modo: Literal["turnar", "vitrina", "menu"] = "turnar"
    orient: Literal["horizontal", "vertical"] = "horizontal"
    t: TiemposIn | None = None
    fiestas: Literal["auto", "siempre", "nunca"] = "auto"
    suave: bool = False
    margen: int = Field(default=0, ge=0, le=pantallas.MARGEN_MAX)
    simple: bool = False


class TelevisorCambio(BaseModel):
    """Lo que se cambia de un televisor: solo lo que viene."""
    nombre: str | None = Field(default=None, min_length=1, max_length=30)
    modo: Literal["turnar", "vitrina", "menu"] | None = None
    orient: Literal["horizontal", "vertical"] | None = None
    t: dict[str, int] | None = None
    fiestas: Literal["auto", "siempre", "nunca"] | None = None
    suave: bool | None = None
    margen: int | None = Field(default=None, ge=0, le=pantallas.MARGEN_MAX)
    simple: bool | None = None


class TextosIn(BaseModel):
    kicker: str = Field(default="", max_length=pantallas.MAX_FRASE)
    bajada: str = Field(default="", max_length=pantallas.MAX_FRASE)
    marcaTxt: str = Field(default="", max_length=pantallas.MAX_FRASE)
    tituloSug: str = Field(default="", max_length=pantallas.MAX_FRASE)
    pieSug: str = Field(default="", max_length=pantallas.MAX_FRASE)
    cinta: list[str] = Field(default_factory=list, max_length=pantallas.MAX_AVISOS)
    fuente_url: str = Field(default="", max_length=300)
    fuente_cada: int = Field(default=pantallas.FUENTE_CADA_POR_DEFECTO, ge=1, le=240)


class ProbarIn(BaseModel):
    url: str = Field(default="", max_length=300)


def _con_visto(tv: dict) -> dict:
    return {**tv, "visto_hace_s": pantallas.visto_hace(tv["id"])}


def _o_404(id_: int) -> dict:
    tv = pantallas.uno(id_)
    if not tv:
        raise HTTPException(404, "Ese televisor ya no está en la lista.")
    return tv


# ---------------------------------------------------------------------------
# Lo que lee cada televisor
# ---------------------------------------------------------------------------
@router.get("/pantallas/config")
def config_del_televisor(t: int | None = None):
    """Los textos y los ajustes de un televisor. Sin `t`, o con un número que ya no existe, solo
    los textos comunes: así una dirección vieja sigue andando."""
    return pantallas.para_el_televisor(t)


# ---------------------------------------------------------------------------
# Los televisores
# ---------------------------------------------------------------------------
@router.get("/config/televisores")
def listar(quien: dict = Depends(puerta_config.exige())):
    return {"televisores": [_con_visto(t) for t in pantallas.listar()]}


@router.post("/config/televisores")
def crear(datos: TelevisorIn, quien: dict = Depends(puerta_config.exige())):
    return _con_visto(pantallas.crear(datos.model_dump()))


@router.put("/config/televisores/{id_}")
def cambiar(id_: int, datos: TelevisorCambio, quien: dict = Depends(puerta_config.exige())):
    _o_404(id_)
    return _con_visto(pantallas.cambiar(id_, datos.model_dump(exclude_none=True)))


@router.delete("/config/televisores/{id_}")
def quitar(id_: int, quien: dict = Depends(puerta_config.exige())):
    if not pantallas.quitar(id_):
        raise HTTPException(404, "Ese televisor ya no está en la lista.")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Los textos
# ---------------------------------------------------------------------------
@router.get("/config/pantallas")
def ver_textos(quien: dict = Depends(puerta_config.exige())):
    return {"textos": pantallas.textos(), "ejemplo": pantallas.TEXTOS_DE_EJEMPLO}


@router.put("/config/pantallas")
def guardar_textos(datos: TextosIn, quien: dict = Depends(puerta_config.exige())):
    return {"textos": pantallas.guardar_textos(datos.model_dump()),
            "ejemplo": pantallas.TEXTOS_DE_EJEMPLO}


@router.post("/config/pantallas/ejemplo")
def volver_al_ejemplo(quien: dict = Depends(puerta_config.exige())):
    """Borra lo que el dueño escribió en los textos y los avisos: las pantallas vuelven a lo
    suyo. La lista de televisores no cambia."""
    return {"textos": pantallas.guardar_textos({}), "ejemplo": pantallas.TEXTOS_DE_EJEMPLO}


@router.get("/config/pantallas/respaldo")
def bajar_respaldo(quien: dict = Depends(puerta_config.exige())):
    cuerpo = json.dumps(pantallas.respaldo(), ensure_ascii=False, indent=2)
    return Response(cuerpo.encode("utf-8"), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="respaldo-pantallas.json"'})


@router.put("/config/pantallas/respaldo")
def subir_respaldo(datos: dict, quien: dict = Depends(puerta_config.exige())):
    try:
        return pantallas.cargar_respaldo(datos)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/config/pantallas/probar")
def probar_conexion(datos: ProbarIn, quien: dict = Depends(puerta_config.exige())):
    """«Probar la conexión» de la carta que viene de otra dirección: la lee y dice si sirve."""
    url = datos.url.strip()
    if not url:
        return {"ok": True, "vacia": True,
                "detalle": "Todavía no hay dirección: las pantallas usan la carta de esta caja (Inventario)."}
    if not url.lower().startswith(("http://", "https://")):
        return {"ok": False, "detalle": "La dirección tiene que empezar con http:// o https://."}
    try:
        pedido = urllib.request.Request(url, headers={"Accept": "application/json",
                                                      "User-Agent": "Gespoint"})
        with urllib.request.urlopen(pedido, timeout=6) as r:      # noqa: S310 (solo http/https)
            crudo = json.loads(r.read(2_000_000).decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"ok": False, "detalle": "No se pudo leer la carta: la dirección no contestó "
                                        f"({str(e)[:80]}). Las pantallas siguen con la última que tenían."}
    categorias = crudo.get("categorias") if isinstance(crudo, dict) else None
    if not isinstance(categorias, list) or not categorias:
        return {"ok": False, "detalle": "Esa dirección contestó, pero no trae una carta con categorías."}
    productos = sum(len(c.get("productos", [])) for c in categorias if isinstance(c, dict))
    return {"ok": True, "productos": productos,
            "detalle": f"Conectó: {len(categorias)} categorías y {productos} productos."}
