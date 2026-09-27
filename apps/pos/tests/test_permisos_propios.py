"""Permisos por persona: «que solo venda».

El dueño lo pidió mirando su propia caja: quiere a alguien que llegue, abra la caja, venda,
cierre y se vaya. Que no le cambie el inventario y que no vea sus métricas. Con dos roles
fijos eso no se podía armar — un cajero ve El día y entra a la bodega—, y crear un rol nuevo
por cada combinación que pida un local no escala.

Ahora una persona puede tener sus propios permisos, y esos mandan sobre los de su rol.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

from core.config import PERMISOS, TODOS_LOS_PERMISOS, permisos_de, puede


# =============================================================================
# La regla
# =============================================================================

def test_sin_permisos_propios_manda_el_rol():
    """Es lo que tiene el 99% de la gente: nada cambia para quien ya estaba."""
    assert permisos_de("cajero") == frozenset(PERMISOS["cajero"])
    assert permisos_de("dueno") == frozenset(PERMISOS["dueno"])
    assert puede("cajero", "vender") and not puede("cajero", "editar_carta")


def test_los_permisos_propios_mandan_sobre_el_rol():
    solo_vende = "vender,turno_abrir,turno_cerrar"
    assert puede("cajero", "vender", solo_vende)
    # Un cajero normal SÍ los tiene; esta persona no.
    assert puede("cajero", "ver_dia") and not puede("cajero", "ver_dia", solo_vende)
    assert puede("cajero", "inventario") and not puede("cajero", "inventario", solo_vende)


def test_tambien_recortan_a_un_dueno():
    """Si no, restringir a alguien con rol de dueño no serviría de nada."""
    assert puede("dueno", "config")
    assert not puede("dueno", "config", "vender")


def test_el_caso_que_pidio_el_duenno():
    """Llega, abre la caja, vende, cierra y se va."""
    solo_vende = "vender,turno_abrir,turno_cerrar"
    for si in ("vender", "turno_abrir", "turno_cerrar"):
        assert puede("cajero", si, solo_vende), si
    for no in ("ver_dia", "ver_informes", "inventario", "inventario_ajustar",
               "editar_carta", "usuarios", "config", "anular_pasado"):
        assert not puede("cajero", no, solo_vende), no


# =============================================================================
# Que no se pueda colar nada
# =============================================================================

def test_un_permiso_inventado_no_vale():
    """Si alguien escribe cualquier cosa en la base, no se convierte en un permiso."""
    assert not puede("cajero", "borrar_todo", "vender,borrar_todo")
    assert permisos_de("cajero", "vender,borrar_todo") == frozenset({"vender"})


def test_un_permiso_que_se_saque_del_programa_deja_de_valer():
    """Se filtran contra el catálogo, así que retirar uno lo desactiva en todas partes."""
    assert all(p in TODOS_LOS_PERMISOS for p in permisos_de("cajero", "vender,ver_dia"))


@pytest.mark.parametrize("propios", ["", "   ", ",,,", None])
def test_vacio_o_basura_vuelve_al_rol(propios):
    assert permisos_de("cajero", propios) == frozenset(PERMISOS["cajero"])


def test_el_catalogo_y_los_roles_hablan_de_lo_mismo():
    """Un rol con un permiso que no está en el catálogo no se podría ni mostrar ni quitar."""
    for rol, permisos in PERMISOS.items():
        sobran = set(permisos) - set(TODOS_LOS_PERMISOS)
        assert not sobran, f"el rol {rol} tiene permisos fuera del catálogo: {sobran}"


# =============================================================================
# Los sitios donde el permiso se comprueba a mano, fuera de exige()
# =============================================================================

def test_anular_el_pasado_respeta_los_permisos_propios(cliente, carta, caja):
    """Hay dos comprobaciones que no pasan por exige() y es facil olvidarlas.

    Si se olvidan, quitarle un permiso a una persona no sirve de nada justo en las dos
    cosas mas delicadas: anular una venta de una caja ya cerrada y cerrar la caja de otro.
    """
    import apps.pos.api.ventas as ventas
    import apps.pos.api.turnos as turnos
    import inspect

    for modulo, permiso in ((ventas, "anular_pasado"), (turnos, "turno_cerrar_ajeno")):
        fuente = inspect.getsource(modulo)
        i = fuente.find(f'"{permiso}"')
        assert i != -1, f"se movió la comprobación de {permiso}"
        alrededor = fuente[i:i + 120]
        assert "permisos" in alrededor, (
            f"la comprobación de {permiso} no mira los permisos propios de la persona: "
            "quitárselo no tendría efecto")


# =============================================================================
# El candado: que la próxima ruta no se olvide de pedir permiso
# =============================================================================

# Los módulos donde TODA consulta toca algo que se puede restringir. Si mañana alguien
# agrega ahí un GET sin permiso, este test lo caza — que es mejor que una lista de rutas
# escrita en otro archivo, porque esa se desincroniza en silencio y nadie se entera hasta
# que alguien lee algo que no debía.
MODULOS_CON_PERMISO = {
    "inventario.py": "inventario",
    "datos.py": "ver_informes",
}


def test_las_rutas_que_leen_datos_restringidos_piden_permiso():
    """Quitarle la bodega a una persona no servía de nada: las consultas no lo miraban.

    Lo encontró la revisión de Codex al conectar los permisos por persona. Antes daba casi
    igual —un cajero tenía «inventario» de todas formas—, pero desde que se le puede quitar,
    una consulta sin guardia es una puerta abierta con el candado puesto al lado.
    """
    api = Path(__file__).resolve().parents[1] / "api"
    sin_guardia = []
    for archivo, permiso in MODULOS_CON_PERMISO.items():
        fuente = io.open(api / archivo, encoding="utf-8").read()
        for m in re.finditer(r'@router\.get\((["\'])(.+?)\1', fuente):
            trozo = fuente[m.start():m.start() + 320]
            if "sesion.exige(" not in trozo and "Depends(exige(" not in trozo:
                sin_guardia.append(f"{archivo} {m.group(2)}")

    assert not sin_guardia, (
        "estas consultas no piden ningún permiso, así que se pueden leer aunque a la "
        f"persona se le haya quitado: {sin_guardia}")
