"""Qué dejar en la caja al cerrar: que deje el sencillo y que no se pierda una moneda.

El caso principal es real: es el conteo que el dueño hizo a mano una noche y fotografió.
"""

from __future__ import annotations

import pytest

from core.fondo import plan_de_cierre, repartir, repartir_fondo

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


# =============================================================================
# La propina: el mismo problema al revés
# =============================================================================

def test_la_propina_sale_en_billetes_grandes():
    """Las monedas tienen que QUEDARSE en la caja: mañana son el vuelto."""
    r = repartir(REAL, 20000, preferir="grande")
    _cuadra(REAL, r)
    assert r["exacto"] is True
    assert r["dejar"] == {20000: 1}          # un billete, no veinte de mil
    assert sum(r["dejar"].values()) == 1


def test_sacar_la_propina_no_vacia_el_sencillo():
    conteo = {10000: 2, 1000: 5, 100: 30, 50: 20}
    r = repartir(conteo, 10000, preferir="grande")
    _cuadra(conteo, r)
    assert r["dejar"] == {10000: 1}
    assert r["sobre"][100] == 30 and r["sobre"][50] == 20


def test_si_la_propina_no_es_exacta_se_queda_abajo():
    """No se regala plata que no era propina."""
    conteo = {1000: 10}
    r = repartir(conteo, 2500, preferir="grande")
    assert r["total_dejado"] == 2000 and r["exacto"] is False


def test_el_fondo_en_cambio_se_pasa_para_arriba():
    """La misma situación, criterio opuesto: quedarse corto de vuelto mañana es peor."""
    conteo = {1000: 10}
    assert repartir(conteo, 2500, preferir="sencillo")["total_dejado"] == 3000


# =============================================================================
# El cierre completo: propina, fondo y sobre
# =============================================================================

def _las_tres_cuadran(conteo: dict, plan: dict) -> None:
    """La propiedad del cierre: las TRES pilas juntas son exactamente lo contado."""
    for den in conteo:
        repartido = (plan["propina"]["detalle"].get(den, 0)
                     + plan["fondo"]["detalle"].get(den, 0)
                     + plan["sobre"]["detalle"].get(den, 0))
        assert repartido == conteo[den], f"no cuadra la denominación {den}"
    assert (plan["propina"]["total"] + plan["fondo"]["total"]
            + plan["sobre"]["total"]) == plan["contado"]


def test_el_cierre_reparte_las_tres_pilas_sin_perder_una_moneda():
    plan = plan_de_cierre(REAL, propina=18500, fondo=60000)
    _las_tres_cuadran(REAL, plan)
    assert plan["contado"] == 467180


def test_la_propina_sale_primero_para_poder_formarse():
    """Si saliera después del fondo se quedaría sin billetes medianos con qué armarse."""
    plan = plan_de_cierre(REAL, propina=18500, fondo=60000)
    assert plan["propina"]["exacto"] is True
    assert plan["propina"]["total"] == 18500
    assert plan["fondo"]["exacto"] is True
    assert plan["fondo"]["total"] == 60000


def test_un_cierre_sin_propina_es_solo_fondo_y_sobre():
    plan = plan_de_cierre(REAL, propina=0, fondo=60000)
    _las_tres_cuadran(REAL, plan)
    assert plan["propina"]["detalle"] == {} and plan["propina"]["total"] == 0
    assert plan["fondo"]["total"] == 60000


def test_un_cierre_sin_nada_manda_todo_al_sobre():
    plan = plan_de_cierre(REAL, propina=0, fondo=0)
    _las_tres_cuadran(REAL, plan)
    assert plan["sobre"]["total"] == 467180


def test_si_no_alcanza_para_todo_lo_dice_en_vez_de_inventar():
    conteo = {1000: 10}
    plan = plan_de_cierre(conteo, propina=5000, fondo=60000)
    _las_tres_cuadran(conteo, plan)
    assert plan["propina"]["total"] == 5000 and plan["propina"]["exacto"] is True
    assert plan["fondo"]["exacto"] is False      # solo quedaban 5.000
    assert plan["sobre"]["total"] == 0


# =============================================================================
# El endpoint: el mismo reparto, desde la pantalla del cierre
# =============================================================================

def test_el_endpoint_arma_el_plan_con_el_conteo_de_la_pantalla(cliente, caja):
    """La web manda las claves como texto (JSON no tiene claves enteras)."""
    r = cliente.post("/api/v1/turnos/plan-cierre", json={
        "conteo": {"20000": 6, "10000": 23, "5000": 15, "1000": 36,
                   "100": 39, "50": 45, "10": 3},
        "propina": 18500, "fondo": 60000})
    assert r.status_code == 200
    plan = r.json()
    assert plan["contado"] == 467180
    assert plan["propina"]["total"] == 18500 and plan["propina"]["exacto"] is True
    assert plan["fondo"]["total"] == 60000 and plan["fondo"]["exacto"] is True
    # Las tres pilas siguen sumando lo contado, también pasando por la API.
    assert (plan["propina"]["total"] + plan["fondo"]["total"]
            + plan["sobre"]["total"]) == plan["contado"]


def test_el_endpoint_no_escribe_nada(cliente, caja):
    """Es una calculadora: preguntar dos veces tiene que dar lo mismo y no tocar el turno."""
    antes = cliente.get("/api/v1/turnos/actual").json()
    cuerpo = {"conteo": {"1000": 10}, "propina": 2000, "fondo": 5000}
    a = cliente.post("/api/v1/turnos/plan-cierre", json=cuerpo).json()
    b = cliente.post("/api/v1/turnos/plan-cierre", json=cuerpo).json()
    assert a == b
    assert cliente.get("/api/v1/turnos/actual").json() == antes


def test_el_endpoint_aguanta_basura_sin_reventar(cliente, caja):
    for cuerpo in ({}, {"conteo": None}, {"conteo": {"abc": "x", "1000": 5}},
                   {"conteo": {"1000": 5}, "propina": 0, "fondo": 0}):
        r = cliente.post("/api/v1/turnos/plan-cierre", json=cuerpo)
        assert r.status_code == 200, cuerpo
        assert set(r.json()) == {"contado", "propina", "fondo", "sobre"}


def test_un_monto_negativo_lo_rechaza_el_schema(cliente, caja):
    r = cliente.post("/api/v1/turnos/plan-cierre",
                     json={"conteo": {"1000": 5}, "fondo": -100})
    assert r.status_code == 422
