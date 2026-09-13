"""Qué dejar en la caja al cerrar: que deje el sencillo y que no se pierda una moneda.

El caso principal es real: es el conteo que el dueño hizo a mano una noche y fotografió.
"""

from __future__ import annotations

import pytest

from core.fondo import repartir_fondo

# El conteo de esa noche: $467.180 en 167 piezas.
REAL = {20000: 6, 10000: 23, 5000: 15, 2000: 0, 1000: 36, 500: 0, 100: 39, 50: 45, 10: 3}


def suma(reparto: dict) -> int:
    return sum(den * cant for den, cant in reparto.items())


def _cuadra(conteo: dict, r: dict) -> None:
    """La propiedad que no se puede romper nunca: nada se inventa ni se pierde."""
    for den in set(conteo) | set(r["dejar"]) | set(r["sobre"]):
        assert r["dejar"].get(den, 0) + r["sobre"].get(den, 0) == conteo.get(den, 0), den
    assert all(c > 0 for c in r["dejar"].values())
    assert all(c > 0 for c in r["sobre"].values())
    assert suma(r["dejar"]) == r["total_dejado"]


# =============================================================================
# El caso de todas las noches
# =============================================================================

def test_deja_el_fondo_exacto_con_el_conteo_real():
    r = repartir_fondo(REAL, 60000)
    _cuadra(REAL, r)
    assert r["exacto"] is True
    assert r["total_dejado"] == 60000


def test_se_queda_con_el_sencillo():
    """Es el punto del ejercicio: en la caja sirve el sencillo, no los billetes grandes.

    Ojo: NO se queda con todas las monedas, y no es un error. Las monedas de ese conteo
    suman 6.180, y 6.180 más cualquier cantidad de billetes nunca da 60.000 —haría falta
    juntar 53.820 con billetes de mil para arriba—. Así que sacrifica unas pocas monedas
    para poder cuadrar EXACTO, que es lo que evita recontar. Se queda con 120 piezas de
    las 167 contadas.
    """
    r = repartir_fondo(REAL, 60000)
    monedas_dejadas = sum(c for d, c in r["dejar"].items() if d < 1000)
    monedas_contadas = sum(c for d, c in REAL.items() if d < 1000)
    assert monedas_dejadas >= monedas_contadas * 0.9, "casi todo el sencillo se queda"
    assert sum(r["dejar"].values()) == 120


def test_los_billetes_grandes_se_van_al_sobre():
    r = repartir_fondo(REAL, 60000)
    assert r["sobre"].get(20000) == 6      # los seis, ninguno se queda
    assert 20000 not in r["dejar"]


def test_entre_dos_formas_de_llegar_al_mismo_monto_deja_mas_piezas():
    """10 de mil y 1 de diez mil dan lo mismo; en la caja sirven los diez."""
    conteo = {10000: 3, 1000: 15}
    r = repartir_fondo(conteo, 10000)
    _cuadra(conteo, r)
    assert r == {"dejar": {1000: 10}, "sobre": {10000: 3, 1000: 5},
                 "total_dejado": 10000, "exacto": True}


# =============================================================================
# Cuando no se puede
# =============================================================================

def test_si_el_fondo_no_se_puede_formar_lo_dice_en_vez_de_fingir():
    conteo = {20000: 4}
    r = repartir_fondo(conteo, 30000)
    _cuadra(conteo, r)
    assert r["exacto"] is False
    assert r["total_dejado"] == 40000        # el más cercano, y en empate el de arriba


def test_en_empate_gana_el_de_arriba():
    """Quedarse corto de sencillo mañana es peor que mandar un poco menos al sobre."""
    conteo = {1000: 10}
    r = repartir_fondo(conteo, 2500)
    assert r["total_dejado"] == 3000 and r["exacto"] is False


def test_si_no_alcanza_para_el_fondo_se_deja_todo():
    conteo = {1000: 5}
    r = repartir_fondo(conteo, 60000)
    _cuadra(conteo, r)
    assert r["dejar"] == conteo and r["sobre"] == {}
    assert r["exacto"] is False


# =============================================================================
# Bordes que no pueden reventar la caja a las once de la noche
# =============================================================================

@pytest.mark.parametrize("conteo,objetivo", [
    ({}, 60000), (None, 60000), ({20000: 6}, 0), ({}, 0),
    ({1000: 0, 500: 0}, 60000), ({-100: 5, 1000: -2, 500: 4}, 2000),
])
def test_los_bordes_no_revientan(conteo, objetivo):
    r = repartir_fondo(conteo, objetivo)
    assert set(r) == {"dejar", "sobre", "total_dejado", "exacto"}
    assert r["total_dejado"] >= 0


def test_objetivo_cero_manda_todo_al_sobre():
    r = repartir_fondo(REAL, 0)
    _cuadra(REAL, r)
    assert r["dejar"] == {} and r["total_dejado"] == 0 and r["exacto"] is True


def test_un_objetivo_negativo_se_trata_como_cero():
    r = repartir_fondo(REAL, -5000)
    assert r["dejar"] == {} and r["total_dejado"] == 0


def test_un_cajon_enorme_responde_igual_sin_colgarse():
    """Una feria, o una caja que no se vació en semanas. Peor reparto, pero al instante."""
    conteo = {1000: 3000, 500: 3000, 100: 3000}
    r = repartir_fondo(conteo, 60000)
    _cuadra(conteo, r)
    assert r["total_dejado"] == 60000
