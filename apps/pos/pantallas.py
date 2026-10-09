"""Los televisores del local y lo que dicen sus pantallas, guardados en la base de ESTE local.

Hasta la 2.32 todo esto vivía en el navegador de cada televisor (localStorage, desde el panel
«Configurar» de la propia pantalla): el dueño tenía que ir a cada TV para cambiar una frase. Desde
la 2.33 se administra en Config → Pantallas del local y se guarda acá. Cada televisor se lleva lo
suyo al pedir `/api/v1/pantallas/config?t=<su número>`.

Compatibilidad: las direcciones de siempre (`/pantallas?p=1`, `?p=2`, `?tv=1`, `/pantallas/simple`)
siguen andando exactamente igual. Sin `t=` en la dirección, o sin nada guardado acá, la pantalla se
queda con lo que ya tenía: ningún televisor cambia al actualizar.

Dos llaves en la tabla de ajustes (texto JSON; sin tablas nuevas ni migraciones):

  · `televisores`        {"sig": N, "lista": [ {id, nombre, modo, orient, t, fiestas, suave, margen, simple} ]}
  · `pantallas_textos`  {kicker, bajada, marcaTxt, tituloSug, pieSug, cinta[], fuente_url, fuente_cada}

Lo único que no se guarda es «visto hace N minutos»: vive en memoria (se pierde al reiniciar la caja
y el televisor lo repone en cuanto pregunta).
"""
from __future__ import annotations

import json
import time

from apps.pos import local

MODOS = ("turnar", "vitrina", "menu")
ORIENTACIONES = ("horizontal", "vertical")
FIESTAS = ("auto", "siempre", "nunca")

# Cuánto se queda cada cosa, en segundos: lo que ya traían las pantallas (20 / 14 / 12).
TIEMPOS_POR_DEFECTO = {"vitrina": 20, "cat": 14, "reco": 12}
MIN_SEG, MAX_SEG = 5, 180
MARGEN_MAX = 15            # lo que acepta pantallas.html: de 0 a 15 %

# Lo que las pantallas dicen mientras el dueño no escriba otra cosa. Se muestran como sugerencia
# en Config; el televisor, sin texto guardado, usa lo suyo.
TEXTOS_DE_EJEMPLO = {
    "kicker": "Café de especialidad",
    "bajada": "Tostado en Graneros, molido al momento",
    "marcaTxt": "Café de especialidad · Graneros",
    "tituloSug": "Combo sugerido",
    "pieSug": "Se pide en la barra",
}
CAMPOS_DE_TEXTO = tuple(TEXTOS_DE_EJEMPLO)
MAX_FRASE = 70
MAX_AVISOS = 12
MAX_AVISO = 90
FUENTE_CADA_POR_DEFECTO = 10

_visto: dict[int, float] = {}          # televisor → time.time() de la última vez que preguntó


def _json(clave: str, defecto):
    crudo = local._leer(clave).get(clave)
    if not crudo:
        return defecto
    try:
        valor = json.loads(crudo)
    except ValueError:
        return defecto
    return valor if isinstance(valor, type(defecto)) else defecto


def _guardar(clave: str, valor) -> None:
    from sqlmodel import Session
    from apps.pos.db.session import engine
    with Session(engine) as s:
        local.guardar(s, **{clave: json.dumps(valor, ensure_ascii=False)})


# ---------------------------------------------------------------------------
# Un televisor
# ---------------------------------------------------------------------------
def _limpio(texto, largo: int) -> str:
    return " ".join(str(texto or "").split())[:largo]


def _entero(valor, minimo: int, maximo: int, defecto: int) -> int:
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return defecto
    return max(minimo, min(maximo, n))


def normalizar_tv(crudo: dict, id_: int) -> dict:
    """Un televisor con todos sus campos válidos. Lo que falte o venga raro toma el valor de
    siempre, para que una base editada a mano no rompa la pantalla."""
    t = crudo.get("t") if isinstance(crudo.get("t"), dict) else {}
    return {
        "id": id_,
        "nombre": _limpio(crudo.get("nombre"), 30) or f"Televisor {id_}",
        "modo": crudo.get("modo") if crudo.get("modo") in MODOS else "turnar",
        "orient": crudo.get("orient") if crudo.get("orient") in ORIENTACIONES else "horizontal",
        "t": {k: _entero(t.get(k), MIN_SEG, MAX_SEG, v) for k, v in TIEMPOS_POR_DEFECTO.items()},
        "fiestas": crudo.get("fiestas") if crudo.get("fiestas") in FIESTAS else "auto",
        "suave": bool(crudo.get("suave", False)),
        "margen": _entero(crudo.get("margen"), 0, MARGEN_MAX, 0),
        "simple": bool(crudo.get("simple", False)),
    }


def _registro() -> dict:
    r = _json("televisores", {})
    lista = [normalizar_tv(x, int(x["id"])) for x in r.get("lista", [])
             if isinstance(x, dict) and str(x.get("id", "")).isdigit()]
    return {"sig": max(int(r.get("sig", 1) or 1), max([t["id"] for t in lista], default=0) + 1),
            "lista": lista}


def listar() -> list[dict]:
    return _registro()["lista"]


def uno(id_: int) -> dict | None:
    return next((t for t in listar() if t["id"] == id_), None)


def crear(crudo: dict) -> dict:
    r = _registro()
    tv = normalizar_tv(crudo, r["sig"])
    r["lista"].append(tv)
    r["sig"] += 1
    _guardar("televisores", r)
    return tv


def cambiar(id_: int, crudo: dict) -> dict | None:
    r = _registro()
    for i, t in enumerate(r["lista"]):
        if t["id"] == id_:
            nuevo = {**t, **crudo}
            if isinstance(crudo.get("t"), dict):
                nuevo["t"] = {**t["t"], **crudo["t"]}        # un tiempo suelto no borra los otros
            r["lista"][i] = normalizar_tv(nuevo, id_)
            _guardar("televisores", r)
            return r["lista"][i]
    return None


def quitar(id_: int) -> bool:
    r = _registro()
    nueva = [t for t in r["lista"] if t["id"] != id_]
    if len(nueva) == len(r["lista"]):
        return False
    r["lista"] = nueva
    _guardar("televisores", r)       # `sig` no baja: el número de un televisor quitado no se reusa
    _visto.pop(id_, None)
    return True


def reemplazar_todos(lista: list[dict]) -> list[dict]:
    """Para cargar un respaldo: la lista completa, con números nuevos si vienen repetidos."""
    r = {"sig": 1, "lista": []}
    vistos = set()
    for crudo in lista:
        if not isinstance(crudo, dict):
            continue
        try:
            id_ = int(crudo.get("id"))
        except (TypeError, ValueError):
            id_ = 0
        if id_ < 1 or id_ in vistos:
            id_ = max([t["id"] for t in r["lista"]], default=0) + 1
        vistos.add(id_)
        r["lista"].append(normalizar_tv(crudo, id_))
    r["sig"] = max([t["id"] for t in r["lista"]], default=0) + 1
    antes = _registro()
    r["sig"] = max(r["sig"], antes["sig"])          # tampoco se reusan los de antes
    _guardar("televisores", r)
    return r["lista"]


# ---------------------------------------------------------------------------
# Visto hace…
# ---------------------------------------------------------------------------
def marcar_visto(id_: int | None) -> None:
    if id_ is not None and uno(id_):
        _visto[id_] = time.time()


def visto_hace(id_: int) -> int | None:
    """Segundos desde la última vez que ese televisor preguntó por la caja; None si nunca."""
    cuando = _visto.get(id_)
    return None if cuando is None else max(0, int(time.time() - cuando))


# ---------------------------------------------------------------------------
# Los textos de las pantallas
# ---------------------------------------------------------------------------
def normalizar_textos(crudo: dict) -> dict:
    cinta = []
    for frase in (crudo.get("cinta") if isinstance(crudo.get("cinta"), list) else []):
        f = _limpio(frase, MAX_AVISO)
        if f:
            cinta.append(f)
    url = str(crudo.get("fuente_url") or "").strip()[:300]
    if url and not url.lower().startswith(("http://", "https://")):
        url = ""
    salida = {k: _limpio(crudo.get(k), MAX_FRASE) for k in CAMPOS_DE_TEXTO}
    salida.update(cinta=cinta[:MAX_AVISOS], fuente_url=url,
                  fuente_cada=_entero(crudo.get("fuente_cada"), 1, 240, FUENTE_CADA_POR_DEFECTO))
    return salida


def textos() -> dict:
    return normalizar_textos(_json("pantallas_textos", {}))


def guardar_textos(crudo: dict) -> dict:
    t = normalizar_textos(crudo)
    _guardar("pantallas_textos", t)
    return t


def cinta_o(por_defecto: list[str]) -> list[str]:
    """Los avisos que corren abajo: los que escribió el dueño o, si no escribió, los de siempre."""
    return textos()["cinta"] or list(por_defecto)


def respaldo() -> dict:
    return {"gespoint": "pantallas", "version": 1, "textos": textos(), "televisores": listar()}


def cargar_respaldo(crudo: dict) -> dict:
    if not isinstance(crudo, dict) or crudo.get("gespoint") != "pantallas":
        raise ValueError("Ese archivo no es un respaldo de las pantallas de Gespoint.")
    if not isinstance(crudo.get("textos"), dict) or not isinstance(crudo.get("televisores"), list):
        raise ValueError("El respaldo de las pantallas está incompleto.")
    guardar_textos(crudo["textos"])
    reemplazar_todos(crudo["televisores"])
    return respaldo()


def para_el_televisor(id_: int | None) -> dict:
    """Lo que se lleva un televisor: los textos que el dueño escribió (solo esos; lo vacío no
    pisa nada) y, si la dirección trae su número, lo suyo."""
    t = textos()
    textos_escritos = {k: v for k, v in t.items() if v not in ("", [], None) and k != "fuente_cada"}
    if "fuente_url" in textos_escritos:
        textos_escritos["fuente_cada"] = t["fuente_cada"]
    marcar_visto(id_)
    tv = uno(id_) if id_ is not None else None
    return {"textos": textos_escritos, "tv": tv}
