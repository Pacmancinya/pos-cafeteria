"""Reportes (Ventas → Reportes) y el corte de «Mi turno».

Lo que se cuida acá es lo que no se ve a simple vista:

  · que el PIN lo verifique el SERVIDOR, que expire a los 5 minutos sin uso y que
    cada endpoint exija el permiso (no solo la pantalla);
  · que las cifras sean las del DÍA DEL LOCAL (America/Santiago), no las del día UTC;
  · que las ventas anuladas no cuenten en nada;
  · que la comparación con el período anterior corte a la misma hora;
  · que «Mi turno» muestre la misma cuenta del cajón que el cierre.

Los datos se insertan directo en la base con la hora que se quiere: las ventas de
verdad nacen con la hora de ahora y así no se puede probar un cruce de medianoche.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, select

from apps.pos import sesion
from apps.pos.api import reportes
from apps.pos.db.models import (Ajuste, Insumo, Pago, Receta, Turno, Usuario, Venta,
                                VentaLinea)
from apps.pos.db.session import engine
from core.config import ZONA

# Jueves 8 de octubre de 2026, 14:22 en Santiago (UTC-3 desde el 6 de septiembre).
AHORA = datetime(2026, 10, 8, 14, 22, tzinfo=ZONA).astimezone(timezone.utc)


def L(mes, dia, hora=0, minuto=0, anio=2026):
    """Una hora de reloj de Santiago, en UTC: lo que guarda la base."""
    return datetime(anio, mes, dia, hora, minuto, tzinfo=ZONA).astimezone(timezone.utc)


@pytest.fixture(autouse=True)
def _ahora_fijo(monkeypatch):
    monkeypatch.setattr(reportes, "ahora", lambda: AHORA)


# ---------------------------------------------------------------------------
# El mundo de prueba
# ---------------------------------------------------------------------------
@pytest.fixture()
def mundo(cliente):
    """Un local con dos personas, tres productos y ventas repartidas en el tiempo."""
    ruperto = cliente.post("/api/v1/usuarios", json={"nombre": "Ruperto", "pin": "1234"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": ruperto["id"], "pin": "1234"})
    ana = cliente.post("/api/v1/usuarios", json={
        "nombre": "Ana", "pin": "4321", "rol": "cajero"}).json()
    cafe = cliente.post("/api/v1/categorias", json={"nombre": "Café"}).json()
    dulce = cliente.post("/api/v1/categorias", json={"nombre": "Dulce", "orden": 1}).json()

    def prod(cat, nombre, precio, **extra):
        r = cliente.post("/api/v1/productos", json={
            "categoria_id": cat["id"], "nombre": nombre, "precio": precio, **extra})
        assert r.status_code == 200, r.text
        return r.json()

    latte = prod(cafe, "Latte", 3000, llevar_cuenta=True, costo=1000, stock_inicial=100)  # insumo propio
    alfajor = prod(dulce, "Alfajor", 2000, costo=500)          # costo de referencia
    brownie = prod(dulce, "Brownie", 2500)                     # sin costo

    n = {"numero": 0}

    def turno(uid, nombre, abre, cierra=None, dif=None):
        with Session(engine) as s:
            t = Turno(cajero=nombre, abierto_por_id=uid, abierto_at=abre, cerrado_at=cierra,
                      cerrado_por_id=uid if cierra else None, monto_inicial=10000,
                      diferencia=dif, efectivo_contado=None if dif is None else 10000 + dif)
            s.add(t)
            s.commit()
            return t.id

    def venta(cuando, lineas, tid, uid, medio="efectivo", descuento=0, propina=0,
              estado="pagada", pagos=None):
        """lineas: [(producto|None, nombre, subtotal, cantidad)]"""
        n["numero"] += 1
        with Session(engine) as s:
            v = Venta(numero=n["numero"], turno_id=tid, creada_at=cuando, estado=estado,
                      total=sum(l[2] for l in lineas), descuento=descuento, propina=propina,
                      medio_pago="mixto" if pagos else medio, usuario_id=uid,
                      anulada_at=cuando if estado == "anulada" else None,
                      anulada_motivo="error" if estado == "anulada" else "")
            s.add(v)
            s.flush()
            for pr, nombre, sub, cant in lineas:
                s.add(VentaLinea(venta_id=v.id, producto_id=pr["id"] if pr else None,
                                 nombre=nombre, precio_unitario=sub // cant,
                                 cantidad=cant, subtotal=sub))
            for medio_parte, monto in (pagos or {}).items():
                s.add(Pago(venta_id=v.id, medio=medio_parte, monto=monto))
            s.commit()
            return v.id

    t_viejo = turno(ruperto["id"], "Ruperto", L(9, 20, 9), L(9, 20, 20), 0)
    t1 = turno(ruperto["id"], "Ruperto", L(10, 1, 9), L(10, 1, 20), -300)
    t2 = turno(ana["id"], "Ana", L(10, 7, 9), L(10, 7, 20), 0)
    t3 = turno(ana["id"], "Ana", L(10, 8, 8, 30))                      # el abierto

    # --- historia: lo único que dice "desde cuándo hay datos" ---
    venta(L(9, 20, 12), [(None, "Varios", 100, 1)], t_viejo, ruperto["id"])
    # --- 1 de octubre (jueves, el equivalente de hoy hace una semana) ---
    venta(L(10, 1, 9, 30), [(latte, "Latte", 3000, 1), (alfajor, "Alfajor", 1000, 1)],
          t1, ruperto["id"])
    venta(L(10, 1, 14, 0), [(alfajor, "Alfajor", 2000, 1)], t1, ruperto["id"])
    venta(L(10, 1, 15, 0), [(latte, "Latte", 7000, 1)], t1, ruperto["id"])   # DESPUÉS de las 14:22
    # --- ayer, 23:30: cae en el 7, no en el 8 aunque en UTC ya sea el 8 ---
    venta(L(10, 7, 23, 30), [(alfajor, "Alfajor", 1500, 1)], t2, ana["id"])
    # --- hoy ---
    venta(L(10, 8, 0, 10), [(alfajor, "Alfajor", 800, 1)], t3, ruperto["id"])            # v4
    venta(L(10, 8, 9, 0), [(latte, "Latte", 3000, 1), (alfajor, "Alfajor", 2000, 1)],
          t3, ana["id"])                                                                 # v1
    venta(L(10, 8, 10, 0), [(brownie, "Brownie", 2500, 1), (None, "Varios", 500, 1)],
          t3, ana["id"], medio="debito", propina=300)                                    # v2
    venta(L(10, 8, 13, 0), [(latte, "Latte", 3000, 1), (alfajor, "Alfajor", 1000, 1)],
          t3, ruperto["id"], descuento=1000)                                             # v3
    venta(L(10, 8, 11, 0), [(latte, "Latte", 9000, 3)], t3, ana["id"], estado="anulada")

    return {"cliente": cliente, "ruperto": ruperto, "ana": ana, "latte": latte,
            "alfajor": alfajor, "brownie": brownie, "t_viejo": t_viejo,
            "t1": t1, "t2": t2, "t3": t3, "venta": venta, "turno": turno}


def entrar_a_reportes(cliente, pin="1234"):
    r = cliente.post("/api/v1/reportes/entrar", json={"pin": pin})
    assert r.status_code == 200, r.text
    return r.json()


def ver(cliente, ruta, **params):
    r = cliente.get("/api/v1/reportes/" + ruta, params=params)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# El acceso
# ---------------------------------------------------------------------------
RUTAS = ["resumen?periodo=hoy", "calor?periodo=hoy", "productos?periodo=hoy",
         "cajeros?periodo=hoy", "turnos?periodo=hoy", "turnos/1", "exportar?periodo=hoy"]


@pytest.mark.parametrize("ruta", RUTAS)
def test_sin_el_pin_ningun_endpoint_de_reportes_responde(mundo, ruta):
    """Estar en la caja no alcanza: Reportes pide el PIN, y lo pide el servidor."""
    assert mundo["cliente"].get("/api/v1/reportes/" + ruta).status_code == 401


def test_el_pin_incorrecto_no_abre(mundo):
    c = mundo["cliente"]
    r = c.post("/api/v1/reportes/entrar", json={"pin": "0000"})
    assert r.status_code == 401
    assert "PIN incorrecto" in r.json()["detail"]
    assert c.get("/api/v1/reportes/resumen").status_code == 401


def test_con_el_pin_del_dueno_entra_y_ve_las_cifras(mundo):
    c = mundo["cliente"]
    d = entrar_a_reportes(c)
    assert d["usuario"]["nombre"] == "Ruperto" and d["minutos"] == 5
    assert "pos_reportes" in c.cookies
    assert ver(c, "resumen", periodo="hoy")["actual"]["total"] == 11800


def test_el_pin_de_otra_persona_tambien_sirve_si_ella_tiene_permiso(mundo):
    """Se escribe solo el PIN: el dueño puede abrir Reportes en la sesión de la cajera."""
    c = mundo["cliente"]
    c.post("/api/v1/sesion/entrar", json={"usuario_id": mundo["ana"]["id"], "pin": "4321"})
    assert entrar_a_reportes(c, "1234")["usuario"]["nombre"] == "Ruperto"
    assert c.get("/api/v1/reportes/resumen?periodo=hoy").status_code == 200


def test_quien_no_tiene_el_permiso_recibe_403_con_su_nombre(mundo):
    c = mundo["cliente"]
    r = c.post("/api/v1/usuarios", json={"nombre": "Javi", "pin": "5555",
                                         "permisos": "vender,ver_dia,turno_abrir"})
    assert r.status_code == 200
    r = c.post("/api/v1/reportes/entrar", json={"pin": "5555"})
    assert r.status_code == 403
    assert r.json()["detail"] == "Javi no tiene permiso para ver reportes."
    assert "pos_reportes" not in c.cookies
    assert c.get("/api/v1/reportes/resumen?periodo=hoy").status_code == 401


def test_reportes_es_del_dueno_y_el_cajero_no_entra_de_fabrica(mundo):
    """El dueño lo pidió así: Reportes muestra ganancia y lo que vende cada cajero."""
    from core.config import CATALOGO_DE_PERMISOS, PERMISOS, puede

    assert "ver_reportes" in PERMISOS["dueno"] and "ver_reportes" not in PERMISOS["cajero"]
    assert ("ver_reportes", "Ver reportes") in CATALOGO_DE_PERMISOS
    assert "ver_dia" in PERMISOS["cajero"]            # su turno lo sigue viendo
    assert puede("dueno", "ver_reportes") and not puede("cajero", "ver_reportes")
    c = mundo["cliente"]
    r = c.post("/api/v1/reportes/entrar", json={"pin": "4321"})        # Ana, cajera
    assert r.status_code == 403
    assert entrar_a_reportes(c)["usuario"]["nombre"] == "Ruperto"


def test_quitarle_el_permiso_surte_efecto_al_toque(mundo):
    """El permiso se vuelve a mirar en cada petición, no solo al entrar."""
    c = mundo["cliente"]
    r = c.put(f"/api/v1/usuarios/{mundo['ana']['id']}", json={
        "nombre": "Ana", "rol": "cajero", "permisos": "vender,ver_dia,ver_reportes"})
    assert r.status_code == 200                       # el dueño se lo dio a mano
    entrar_a_reportes(c, "4321")
    assert c.get("/api/v1/reportes/resumen?periodo=hoy").status_code == 200
    r = c.put(f"/api/v1/usuarios/{mundo['ana']['id']}", json={
        "nombre": "Ana", "rol": "cajero", "permisos": "vender,ver_dia"})
    assert r.status_code == 200
    assert c.get("/api/v1/reportes/resumen?periodo=hoy").status_code == 403


def test_a_los_cinco_minutos_sin_uso_se_acaba(mundo, monkeypatch):
    c = mundo["cliente"]
    entrar_a_reportes(c)
    real = sesion.ahora
    monkeypatch.setattr(sesion, "ahora", lambda: real() + timedelta(minutes=6))
    r = c.get("/api/v1/reportes/resumen?periodo=hoy")
    assert r.status_code == 401 and "5 minutos" in r.json()["detail"]
    assert c.get("/api/v1/reportes/estado").json()["activo"] is False


def test_cada_uso_renueva_los_cinco_minutos(mundo, monkeypatch):
    c = mundo["cliente"]
    entrar_a_reportes(c)
    real = sesion.ahora
    monkeypatch.setattr(sesion, "ahora", lambda: real() + timedelta(minutes=4))
    assert c.get("/api/v1/reportes/resumen?periodo=hoy").status_code == 200   # renueva
    monkeypatch.setattr(sesion, "ahora", lambda: real() + timedelta(minutes=8))
    assert c.get("/api/v1/reportes/resumen?periodo=hoy").status_code == 200   # 4 min después
    monkeypatch.setattr(sesion, "ahora", lambda: real() + timedelta(minutes=14))
    assert c.get("/api/v1/reportes/resumen?periodo=hoy").status_code == 401   # 6 min sin uso


def test_el_latido_mantiene_abierto_y_salir_cierra(mundo):
    c = mundo["cliente"]
    assert c.get("/api/v1/reportes/estado").json() == {"activo": False, "motivo": "Reportes pide el PIN."}
    entrar_a_reportes(c)
    e = c.get("/api/v1/reportes/estado").json()
    assert e["activo"] is True and e["usuario"]["nombre"] == "Ruperto"
    c.post("/api/v1/reportes/salir")
    assert c.get("/api/v1/reportes/estado").json()["activo"] is False
    assert c.get("/api/v1/reportes/resumen?periodo=hoy").status_code == 401


def test_la_galleta_de_la_sesion_no_sirve_como_acceso_a_reportes(mundo):
    c = mundo["cliente"]
    c.cookies.set("pos_reportes", c.cookies.get("pos_sesion"))
    assert c.get("/api/v1/reportes/resumen?periodo=hoy").status_code == 401


def test_cinco_pin_malos_frenan_los_intentos(mundo):
    c = mundo["cliente"]
    for _ in range(5):
        c.post("/api/v1/reportes/entrar", json={"pin": "9999"})
    assert c.post("/api/v1/reportes/entrar", json={"pin": "1234"}).status_code == 429


def test_sin_sesion_tampoco_se_puede_pedir_el_pin(mundo):
    c = mundo["cliente"]
    c.post("/api/v1/sesion/salir", json={"por": "salir"})
    assert c.post("/api/v1/reportes/entrar", json={"pin": "1234"}).status_code == 401


def test_la_caja_sin_usuarios_deja_entrar_sin_pin_porque_no_hay_ninguno(cliente):
    """Igual que el resto de la caja: sin personas creadas, nadie queda afuera."""
    r = cliente.post("/api/v1/reportes/entrar", json={})
    assert r.status_code == 200 and r.json()["usuario"]["nombre"] == ""
    assert cliente.get("/api/v1/reportes/resumen?periodo=hoy").status_code == 200


def test_quien_tenia_permisos_propios_con_ver_dia_recibe_ver_reportes_una_sola_vez(mundo):
    """La migración no puede dejar sin Reportes a quien hoy ve El día… ni devolvérselo
    al dueño que se lo quitó a propósito."""
    from apps.pos.db.migraciones import _dar_ver_reportes_a_quien_veia_el_dia

    c = mundo["cliente"]
    javi = c.post("/api/v1/usuarios", json={"nombre": "Javi", "pin": "5555", "rol": "dueno",
                                            "permisos": "vender,ver_dia"}).json()
    cajero = c.post("/api/v1/usuarios", json={"nombre": "Caro", "pin": "7777",
                                              "permisos": "vender,ver_dia"}).json()
    solo = c.post("/api/v1/usuarios", json={"nombre": "Solo", "pin": "6666",
                                            "permisos": "vender"}).json()
    with Session(engine) as s:
        s.delete(s.get(Ajuste, "migracion.ver_reportes"))      # como en una caja que se actualiza
        s.commit()
    assert _dar_ver_reportes_a_quien_veia_el_dia() == [f"usuario {javi['id']}: + ver_reportes"]
    with Session(engine) as s:
        assert s.get(Usuario, javi["id"]).permisos == "vender,ver_dia,ver_reportes"
        assert s.get(Usuario, solo["id"]).permisos == "vender"
        assert s.get(Usuario, cajero["id"]).permisos == "vender,ver_dia"   # cajeros no
    # El dueño se lo quita a propósito: el próximo arranque no se lo devuelve.
    c.put(f"/api/v1/usuarios/{javi['id']}", json={"nombre": "Javi", "permisos": "vender,ver_dia"})
    assert _dar_ver_reportes_a_quien_veia_el_dia() == []
    with Session(engine) as s:
        assert s.get(Usuario, javi["id"]).permisos == "vender,ver_dia"


# ---------------------------------------------------------------------------
# Los períodos
# ---------------------------------------------------------------------------
def p(clave, **kw):
    return reportes.calcular_periodo(clave, ahora_utc=AHORA, **kw)


def test_hoy_se_compara_con_el_mismo_dia_de_la_semana_pasada_cortado_a_la_misma_hora():
    r = p("hoy")
    assert (r["ini"], r["fin"]) == (datetime(2026, 10, 8), datetime(2026, 10, 8, 14, 22))
    assert (r["pini"], r["pfin"]) == (datetime(2026, 10, 1), datetime(2026, 10, 1, 14, 22))
    assert r["en_curso"] and r["vs"] == "el jueves pasado, a esta misma hora"


def test_ayer_y_mes_pasado_son_dias_completos():
    r = p("ayer")
    assert (r["ini"], r["fin"]) == (datetime(2026, 10, 7), datetime(2026, 10, 8))
    assert (r["pini"], r["pfin"]) == (datetime(2026, 9, 30), datetime(2026, 10, 1))
    assert not r["en_curso"]
    m = p("mesp")
    assert (m["ini"], m["fin"]) == (datetime(2026, 9, 1), datetime(2026, 10, 1))
    assert (m["pini"], m["pfin"]) == (datetime(2026, 8, 1), datetime(2026, 9, 1))
    assert len(m["dias"]) == 30


def test_siete_dias_y_este_mes_en_curso_cortan_el_anterior_a_la_misma_hora():
    r = p("7d")
    assert r["ini"] == datetime(2026, 10, 2) and len(r["dias"]) == 7
    assert (r["pini"], r["pfin"]) == (datetime(2026, 9, 25), datetime(2026, 10, 1, 14, 22))
    m = p("mes")
    assert (m["pini"], m["pfin"]) == (datetime(2026, 9, 1), datetime(2026, 9, 8, 14, 22))


def test_el_31_contra_un_mes_mas_corto_compara_todo_el_mes_anterior():
    ahora = datetime(2026, 3, 31, 10, 0, tzinfo=ZONA).astimezone(timezone.utc)
    m = reportes.calcular_periodo("mes", ahora_utc=ahora)
    assert (m["pini"], m["pfin"]) == (datetime(2026, 2, 1), datetime(2026, 3, 1))


def test_un_rango_se_compara_con_los_mismos_dias_anteriores_y_no_pasa_de_hoy():
    r = p("rango", desde="2026-09-20", hasta="2026-09-26")
    assert (r["ini"], r["fin"]) == (datetime(2026, 9, 20), datetime(2026, 9, 27))
    assert (r["pini"], r["pfin"]) == (datetime(2026, 9, 13), datetime(2026, 9, 20))
    assert not r["en_curso"] and r["vs"] == "los 7 días anteriores"
    futuro = p("rango", desde="2026-10-06", hasta="2026-12-31")
    assert futuro["dias"][-1].isoformat() == "2026-10-08" and futuro["en_curso"]
    invertido = p("rango", desde="2026-09-26", hasta="2026-09-20")
    assert invertido["ini"] == datetime(2026, 9, 20)


def test_periodos_invalidos_dan_422(mundo):
    c = mundo["cliente"]
    entrar_a_reportes(c)
    assert c.get("/api/v1/reportes/resumen?periodo=siglo").status_code == 422
    assert c.get("/api/v1/reportes/resumen?periodo=rango&desde=mañana").status_code == 422
    assert c.get("/api/v1/reportes/resumen?periodo=rango&desde=2020-01-01&hasta=2026-10-01"
                 ).status_code == 422


# ---------------------------------------------------------------------------
# Las cifras
# ---------------------------------------------------------------------------
def test_hoy_suma_lo_cobrado_sin_las_anuladas_y_con_el_descuento_aplicado(mundo):
    c = mundo["cliente"]
    entrar_a_reportes(c)
    r = ver(c, "resumen", periodo="hoy")
    a = r["actual"]
    # v4 800 + v1 5000 + v2 3000 + v3 (4000 − 1000) = 11.800; la anulada de 9.000 no cuenta.
    assert (a["total"], a["n"], a["ticket"]) == (11800, 4, 2950)
    assert a["propinas"] == 300
    assert a["anuladas"] == {"n": 1, "total": 9000}
    assert (r["desde"], r["hasta"], r["un_dia"], r["en_curso"], r["corte"]) == \
        ("2026-10-08", "2026-10-08", True, True, "14:22")


def test_la_venta_de_las_23_30_de_ayer_no_es_de_hoy_aunque_en_utc_ya_sea_el_8(mundo):
    """Cruce de medianoche: 23:30 en Santiago son las 02:30 UTC del día siguiente."""
    c = mundo["cliente"]
    entrar_a_reportes(c)
    assert L(10, 7, 23, 30).day == 8                       # en UTC ya es el 8…
    assert ver(c, "resumen", periodo="ayer")["actual"]["total"] == 1500
    hoy = ver(c, "resumen", periodo="hoy")
    assert hoy["actual"]["total"] == 11800                 # …y no se mezcla con hoy
    por_hora = {h["hora"]: h["total"] for h in hoy["por_hora"]}
    assert por_hora[0] == 800                              # la de las 00:10 sí es de hoy


def test_el_cambio_de_hora_de_septiembre_no_corre_la_venta_de_dia(cliente):
    """En Chile el reloj salta de las 24:00 del sábado a las 01:00: 03:30 UTC todavía es
    el sábado a las 23:30 y 04:30 UTC ya es el domingo a la 01:30."""
    with Session(engine) as s:
        s.add(Venta(numero=1, creada_at=datetime(2026, 9, 6, 3, 30), total=1000))
        s.add(Venta(numero=2, creada_at=datetime(2026, 9, 6, 4, 30), total=2000))
        s.commit()
    cliente.post("/api/v1/reportes/entrar", json={})
    r = ver(cliente, "resumen", periodo="rango", desde="2026-09-05", hasta="2026-09-07")
    dias = {d["fecha"]: d["total"] for d in r["por_dia"]}
    assert dias == {"2026-09-05": 1000, "2026-09-06": 2000, "2026-09-07": 0}


def test_la_comparacion_corta_el_periodo_anterior_a_la_misma_hora(mundo):
    c = mundo["cliente"]
    entrar_a_reportes(c)
    r = ver(c, "resumen", periodo="hoy")
    # El jueves 1° hasta las 14:22: 4.000 (9:30) + 2.000 (14:00). Las 7.000 de las 15:00
    # no entran: comparar contra el día entero diría que hoy va perdiendo.
    assert r["hay_previo"] is True
    assert (r["previo"]["total"], r["previo"]["n"]) == (6000, 2)
    assert r["vs"] == "el jueves pasado, a esta misma hora"


def test_sin_historia_suficiente_no_se_compara(mundo):
    """Este mes se compara con septiembre 1–8, y el local tiene datos recién desde el 20."""
    c = mundo["cliente"]
    entrar_a_reportes(c)
    r = ver(c, "resumen", periodo="mes")
    assert r["hay_previo"] is False and r["previo"] is None
    assert r["actual"]["total"] == 4000 + 2000 + 7000 + 1500 + 11800


def test_siete_dias_por_dia_rellena_con_ceros_y_marca_fin_de_semana(mundo):
    c = mundo["cliente"]
    entrar_a_reportes(c)
    r = ver(c, "resumen", periodo="7d")
    dias = {d["fecha"]: d for d in r["por_dia"]}
    assert list(dias) == ["2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05",
                          "2026-10-06", "2026-10-07", "2026-10-08"]
    assert dias["2026-10-07"]["total"] == 1500 and dias["2026-10-08"]["total"] == 11800
    assert dias["2026-10-04"]["fin_de_semana"] and not dias["2026-10-05"]["fin_de_semana"]
    assert dias["2026-10-03"]["total"] == 0
    assert r["por_hora"] == []                              # varias fechas: no hay serie por hora
    assert r["previo"]["total"] == 6000                    # 25 sep – 1 oct 14:22


def test_formas_de_pago_reparten_el_pago_mixto_por_partes(mundo):
    c = mundo["cliente"]
    mundo["venta"](L(10, 8, 12, 0), [(mundo["latte"], "Latte", 4000, 1)], mundo["t3"],
                   mundo["ana"]["id"], pagos={"efectivo": 1500, "debito": 2500})
    entrar_a_reportes(c)
    r = ver(c, "resumen", periodo="hoy")
    medios = {m["medio"]: m for m in r["por_medio"]}
    assert medios["efectivo"]["total"] == 8800 + 1500 and medios["efectivo"]["n"] == 3 + 1
    assert medios["debito"]["total"] == 3000 + 2500 and medios["debito"]["n"] == 1 + 1
    assert r["n_mixtas"] == 1
    assert r["actual"]["total"] == 11800 + 4000
    assert sum(m["total"] for m in r["por_medio"]) == r["actual"]["total"]
    assert r["propinas"] == {"total": 300, "efectivo": 0, "tarjeta": 300, "n": 1}


def test_las_categorias_reparten_el_descuento_y_suman_lo_vendido(mundo):
    c = mundo["cliente"]
    entrar_a_reportes(c)
    r = ver(c, "resumen", periodo="hoy")
    cats = {f["nombre"]: f["total"] for f in r["por_categoria"]}
    # v3 (4.000 con 1.000 de descuento): Latte 2.250 y Alfajor 750.
    assert cats == {"Café": 3000 + 2250, "Dulce": 2000 + 750 + 800 + 2500, "Sin categoría": 500}
    assert sum(cats.values()) == r["actual"]["total"] == 11800
    assert [f["nombre"] for f in r["por_categoria"]][0] == "Dulce"          # de mayor a menor


def test_ganancia_estimada_solo_cuenta_lo_que_tiene_costo(mundo):
    c = mundo["cliente"]
    entrar_a_reportes(c)
    r = ver(c, "resumen", periodo="hoy")
    a = r["actual"]
    # Con costo: Latte (insumo propio $1.000) y Alfajor (referencia $500).
    #   v1 Latte 3.000−1.000 + Alfajor 2.000−500   · v3 Latte 2.250−1.000 + Alfajor 750−500
    #   v4 Alfajor 800−500                         = 2.000+1.500+1.250+250+300 = 5.300
    assert a["venta_con_costo"] == 3000 + 2000 + 2250 + 750 + 800
    assert a["ganancia"] == 5300
    assert a["margen"] == round(5300 / 8800 * 100)
    # Brownie (sin costo) y el cobro a mano no cuentan: se informan aparte.
    assert a["venta_sin_costo"] == 3000
    assert r["productos_sin_costo"] == 1                   # Brownie
    # El período anterior usa los mismos costos: 1 de oct hasta las 14:22.
    assert r["previo"]["ganancia"] == (3000 - 1000) + (1000 - 500) + (2000 - 500)


def test_el_costo_de_una_receta_antigua_es_la_suma_de_sus_ingredientes(mundo):
    c = mundo["cliente"]
    cat = c.post("/api/v1/categorias", json={"nombre": "Comida"}).json()
    sandwich = c.post("/api/v1/productos", json={
        "categoria_id": cat["id"], "nombre": "Sándwich", "precio": 4000}).json()
    with Session(engine) as s:
        jamon = Insumo(nombre="Jamón", unidad="g", compra_contenido=1000, compra_costo=8000)
        pan = Insumo(nombre="Pan", unidad="un", compra_contenido=10, compra_costo=2000)
        s.add(jamon)
        s.add(pan)
        s.flush()
        s.add(Receta(producto_id=sandwich["id"], insumo_id=jamon.id, cantidad=50))   # $400
        s.add(Receta(producto_id=sandwich["id"], insumo_id=pan.id, cantidad=2))      # $400
        s.commit()
    mundo["venta"](L(10, 8, 12, 30), [(sandwich, "Sándwich", 4000, 1)], mundo["t3"],
                   mundo["ana"]["id"])
    entrar_a_reportes(c)
    assert reportes.costos_por_producto(Session(engine))[sandwich["id"]] == 800
    r = ver(c, "resumen", periodo="hoy")
    assert r["actual"]["ganancia"] == 5300 + (4000 - 800)


def test_una_linea_de_balanza_no_entra_en_la_ganancia(mundo):
    """Se cobra por peso: «cuánto cuesta una unidad» no existe."""
    c = mundo["cliente"]
    entrar_a_reportes(c)
    antes = ver(c, "resumen", periodo="hoy")["actual"]
    v = mundo["venta"](L(10, 8, 12, 40), [(mundo["latte"], "Latte", 1500, 1)], mundo["t3"],
                       mundo["ana"]["id"])
    with Session(engine) as s:
        for l in s.exec(select(VentaLinea).where(VentaLinea.venta_id == v)).all():
            l.codigo_balanza = "2012345"
            s.add(l)
        s.commit()
    despues = ver(c, "resumen", periodo="hoy")["actual"]
    assert despues["total"] == antes["total"] + 1500
    assert despues["ganancia"] == antes["ganancia"]
    assert despues["venta_sin_costo"] == antes["venta_sin_costo"] + 1500


def test_el_mapa_de_calor_promedia_por_dia_de_la_semana(mundo):
    c = mundo["cliente"]
    entrar_a_reportes(c)
    r = ver(c, "calor", periodo="hoy")
    # Menos de 14 días: se usan las últimas 4 semanas (11 sep – 8 oct = 28 días).
    assert r["ultimas_4_semanas"] is True and r["dias"] == 28
    assert r["ocurrencias"] == [4] * 7
    jueves, nueve = 3, 9
    assert r["celdas"][jueves][nueve] == round((4000 + 5000) / 4)       # jueves 1 y 8, 9 h
    assert r["todos"][nueve] == round((4000 + 5000) / 28)
    assert (r["hora_ini"], r["hora_fin"]) == (0, 23)       # ventas a las 00:10 y a las 23:30
    assert len(r["celdas"]) == 7 and all(len(f) == 24 for f in r["celdas"])


def test_el_mapa_de_calor_con_un_mes_usa_ese_mes(mundo):
    c = mundo["cliente"]
    entrar_a_reportes(c)
    r = ver(c, "calor", periodo="mes")
    assert r["ultimas_4_semanas"] is True                   # 8 días: aún poco
    r = ver(c, "calor", periodo="rango", desde="2026-09-01", hasta="2026-09-30")
    assert r["ultimas_4_semanas"] is False and r["dias"] == 30
    assert r["ocurrencias"][1] == 5                          # cinco martes en septiembre


def test_productos_vendidos_y_sin_ventas_y_los_cobros_a_mano(mundo):
    c = mundo["cliente"]
    entrar_a_reportes(c)
    r = ver(c, "productos", periodo="hoy")
    v = {p["nombre"]: p for p in r["vendidos"]}
    assert v["Alfajor"]["cantidad"] == 3 and v["Alfajor"]["categoria"] == "Dulce"
    assert v["Alfajor"]["total"] == 800 + 2000 + 750
    assert v["Latte"]["cantidad"] == 2 and v["Latte"]["total"] == 3000 + 2250
    assert v["Varios"]["categoria"] == "Cobros a mano" and v["Varios"]["id"] is None
    assert [x["nombre"] for x in r["vendidos"]][0] == "Alfajor"        # por cantidad
    assert "Latte" not in {p["nombre"] for p in r["sin_ventas"]}
    # Ayer solo se vendió un alfajor: Latte y Brownie están sin ventas, con su última venta.
    ayer = ver(c, "productos", periodo="ayer")
    sin = {p["nombre"]: p for p in ayer["sin_ventas"]}
    assert set(sin) == {"Latte", "Brownie"}
    assert sin["Latte"]["ultima_venta"] == "2026-10-08"
    assert sin["Brownie"]["ultima_venta"] == "2026-10-08"


def test_las_anuladas_no_aparecen_en_ninguna_parte(mundo):
    """La anulada de hoy son 3 lattes por $9.000: no están en ventas, ni en productos,
    ni en categorías, ni en el mapa."""
    c = mundo["cliente"]
    entrar_a_reportes(c)
    r = ver(c, "resumen", periodo="hoy")
    assert r["actual"]["total"] == 11800 and r["actual"]["n"] == 4
    latte = next(p for p in ver(c, "productos", periodo="hoy")["vendidos"] if p["nombre"] == "Latte")
    assert latte["cantidad"] == 2
    assert ver(c, "calor", periodo="hoy")["celdas"][3][11] == 0       # la de las 11:00 no está
    cajeros = {f["nombre"]: f for f in ver(c, "cajeros", periodo="hoy")}
    assert cajeros["Ana"]["total"] == 5000 + 3000 and cajeros["Ana"]["n"] == 2


def test_por_cajero_con_ventas_turnos_y_diferencias_de_arqueo(mundo):
    c = mundo["cliente"]
    entrar_a_reportes(c)
    mes = {f["nombre"]: f for f in ver(c, "cajeros", periodo="mes")}
    ruperto, ana = mes["Ruperto"], mes["Ana"]
    assert (ruperto["turnos"], ruperto["cerrados"], ruperto["con_diferencia"]) == (1, 1, 1)
    assert ruperto["diferencia_total"] == -300
    assert ruperto["diferencias"] == [{"turno_id": mundo["t1"], "diferencia": -300,
                                       "fecha": "2026-10-01"}]
    assert (ana["turnos"], ana["cerrados"], ana["con_diferencia"], ana["diferencia_total"]) == (2, 1, 0, 0)
    # Ventas: Ruperto 4.000+2.000+7.000 + 800 + 3.000 (v3); Ana 1.500 + 5.000 + 3.000.
    assert ruperto["total"] == 4000 + 2000 + 7000 + 800 + 3000 and ruperto["n"] == 5
    assert ana["total"] == 1500 + 5000 + 3000 and ana["n"] == 3
    assert [f["nombre"] for f in ver(c, "cajeros", periodo="mes")][0] == "Ruperto"


def test_historial_de_turnos_con_lo_vendido_y_como_cuadro(mundo):
    c = mundo["cliente"]
    entrar_a_reportes(c)
    h = ver(c, "turnos", periodo="mes")
    assert [t["id"] for t in h] == [mundo["t3"], mundo["t2"], mundo["t1"]]       # el más nuevo arriba
    t3, t2, t1 = h
    assert t3["abierto"] and t3["diferencia"] is None and t3["vendido"] == 11800 and t3["n"] == 4
    assert t2["diferencia"] == 0 and t2["vendido"] == 1500
    assert t1["diferencia"] == -300 and t1["vendido"] == 13000 and t1["abrio"] == "Ruperto"
    assert ver(c, "turnos", periodo="hoy")[0]["id"] == mundo["t3"]
    assert len(ver(c, "turnos", periodo="hoy")) == 1


def test_exportar_baja_el_csv_del_periodo_sin_pedir_el_permiso_de_informes(mundo):
    c = mundo["cliente"]
    # Una persona con Reportes pero SIN «ver_informes» (el permiso de los CSV de siempre).
    c.post("/api/v1/usuarios", json={"nombre": "Contadora", "pin": "7777",
                                     "permisos": "ver_dia,ver_reportes"})
    c.post("/api/v1/sesion/entrar", json={
        "usuario_id": next(u for u in c.get("/api/v1/candado").json()["usuarios"]
                           if u["nombre"] == "Contadora")["id"], "pin": "7777"})
    assert c.get("/api/v1/exportar/ventas").status_code == 403
    assert c.get("/api/v1/reportes/exportar?periodo=hoy").status_code == 401
    entrar_a_reportes(c, "7777")
    r = c.get("/api/v1/reportes/exportar?periodo=hoy&tipo=ventas")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    texto = r.content.decode("utf-8-sig")
    assert "Fecha;Hora" in texto and "ventas_2026-10-08_a_2026-10-08" in r.headers["content-disposition"]
    assert texto.count("\r\n") == 1 + 5                      # cabecera + 4 pagadas + 1 anulada de hoy
    d = c.get("/api/v1/reportes/exportar?periodo=7d&tipo=detalle")
    assert d.status_code == 200 and "Producto" in d.content.decode("utf-8-sig")
    assert c.get("/api/v1/reportes/exportar?tipo=otro").status_code == 422


# ---------------------------------------------------------------------------
# «Mi turno» y el corte de un turno
# ---------------------------------------------------------------------------
def test_el_corte_de_un_turno_cierra_la_cuenta_del_cajon_como_el_cierre(caja, carta):
    """fondo + ventas en efectivo + entradas − retiros − devoluciones = lo que debería haber,
    y es EXACTAMENTE la cifra del cierre."""
    c = caja
    c.post("/api/v1/turnos/cerrar", json={"conteo": {}, "efectivo_contado": 0})
    c.post("/api/v1/turnos/abrir", json={"cajero": "Prueba", "conteo": {"10000": 5}})
    latte, alfajor = carta["latte"]["id"], carta["alfajor"]["id"]
    v1 = c.post("/api/v1/ventas", json={"lineas": [{"producto_id": latte, "cantidad": 2}],
                                        "medio_pago": "efectivo"}).json()
    v2 = c.post("/api/v1/ventas", json={"lineas": [{"producto_id": alfajor, "cantidad": 1}],
                                        "medio_pago": "efectivo"}).json()
    c.post("/api/v1/ventas", json={"lineas": [{"producto_id": latte, "cantidad": 1}],
                                   "medio_pago": "debito", "propina": 340})
    c.post(f"/api/v1/ventas/{v2['id']}/anular", json={"motivo": "error al cobrar"})
    assert c.post("/api/v1/turnos/retiro", json={"monto": 4000, "motivo": "pan"}).status_code == 200
    assert c.post("/api/v1/turnos/ingreso", json={"monto": 5000, "motivo": "cambio"}).status_code == 200

    actual = c.get("/api/v1/turnos/actual").json()["turno"]
    cj = c.get(f"/api/v1/turnos/{actual['id']}/corte").json()
    k = cj["caja"]
    assert k["fondo"] == 50000
    assert k["ventas_efectivo"] == 6800 + 1900 and k["devoluciones"] == 1900
    assert (k["entradas"], k["retiros"]) == (5000, 4000)
    suma = (k["fondo"] + k["ventas_efectivo"] + k["entradas"] - k["retiros"]
            - k["devoluciones"] - k["propinas_pagadas"])
    assert suma == k["esperado"] == actual["efectivo_esperado"] == 50000 + 6800 + 5000 - 4000
    assert (cj["vendido"], cj["n"]) == (6800 + 3400, 3 - 1)
    assert cj["anuladas"] == {"n": 1, "total": 1900}
    assert cj["propinas"] == {"efectivo": 0, "tarjeta": 340, "total": 340, "n": 1}
    medios = {m["medio"]: m for m in cj["por_medio"]}
    assert medios["efectivo"]["total"] == 6800 and medios["debito"]["total"] == 3400
    assert {m["tipo"] for m in cj["movimientos"]} == {"retiro", "ingreso"}
    assert [v["numero"] for v in cj["ventas"]] == sorted((v["numero"] for v in cj["ventas"]),
                                                         reverse=True)
    anulada = next(v for v in cj["ventas"] if v["anulada"])
    assert anulada["numero"] == v2["numero"] and anulada["anulada_motivo"] == "error al cobrar"
    assert anulada["productos"] == [{"nombre": "Alfajor", "cantidad": 1}]
    cats = {f["nombre"]: f["total"] for f in cj["por_categoria"]}
    assert cats == {"Café": 6800 + 3400}
    assert cj["cierre"] is None and cj["turno"]["abierto"] is True


def test_el_retiro_no_deja_sacar_mas_de_lo_que_hay_y_la_entrada_no_tiene_tope(caja):
    assert caja.post("/api/v1/turnos/retiro", json={"monto": 99999, "motivo": "x"}).status_code == 409
    assert caja.post("/api/v1/turnos/ingreso", json={"monto": 99999, "motivo": "aporte"}).status_code == 200


def test_la_entrada_de_efectivo_suma_al_deberia_haber_y_anularla_la_resta(caja):
    t = caja.get("/api/v1/turnos/actual").json()["turno"]
    antes = caja.get(f"/api/v1/turnos/{t['id']}/corte").json()["caja"]["esperado"]
    r = caja.post("/api/v1/turnos/ingreso", json={"monto": 7000, "motivo": "monedas"}).json()
    mov = next(m for m in r["retiros"] if m["tipo"] == "ingreso")
    corte = caja.get(f"/api/v1/turnos/{t['id']}/corte").json()
    assert corte["caja"]["entradas"] == 7000
    assert corte["caja"]["esperado"] == antes + 7000
    caja.post(f"/api/v1/turnos/retiro/{mov['id']}/anular")
    corte = caja.get(f"/api/v1/turnos/{t['id']}/corte").json()
    assert corte["caja"]["entradas"] == 0 and corte["caja"]["esperado"] == antes


def test_cerrar_el_turno_guarda_lo_mismo_de_siempre_y_el_corte_lo_muestra(caja, carta):
    """El cierre y el arqueo no cambiaron: lo guardado es lo contado menos lo esperado."""
    c = caja
    c.post("/api/v1/ventas", json={"lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 2}],
                                   "medio_pago": "efectivo"})
    c.post("/api/v1/ventas", json={"lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
                                   "medio_pago": "debito"})
    t = c.get("/api/v1/turnos/actual").json()["turno"]
    assert t["efectivo_esperado"] == 6800
    r = c.post("/api/v1/turnos/cerrar", json={
        "conteo": {"5000": 1, "1000": 1, "500": 1}, "fondo_siguiente": 0,
        "medios": {"debito": 3400}, "nota": "ok"})
    assert r.status_code == 200
    cerrado = r.json()
    assert cerrado["efectivo_contado"] == 6500 and cerrado["diferencia"] == -300
    assert cerrado["conteo_cierre"] == {"5000": 1, "1000": 1, "500": 1}
    assert cerrado["medios"][0]["diferencia"] == 0
    corte = c.get(f"/api/v1/turnos/{t['id']}/corte").json()
    assert corte["cierre"]["contado"] == 6500 and corte["cierre"]["diferencia"] == -300
    assert corte["cierre"]["conteo"] == {"5000": 1, "1000": 1, "500": 1}
    assert corte["cierre"]["medios"][0]["declarado"] == 3400
    assert corte["caja"]["esperado"] == 6800 and corte["turno"]["abierto"] is False
    # …y el historial de Reportes abre el mismo corte, solo con el acceso de Reportes.
    assert c.get(f"/api/v1/reportes/turnos/{t['id']}").status_code == 401
    c.post("/api/v1/reportes/entrar", json={})
    igual = c.get(f"/api/v1/reportes/turnos/{t['id']}").json()
    assert igual == corte
    assert c.get("/api/v1/reportes/turnos/9999").status_code == 404
    assert c.get("/api/v1/turnos/9999/corte").status_code == 404


def test_el_corte_pide_ver_ventas(cliente):
    d = cliente.post("/api/v1/usuarios", json={"nombre": "Ruperto", "pin": "1234"}).json()
    assert cliente.get("/api/v1/turnos/1/corte").status_code == 401        # sin sesión
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": d["id"], "pin": "1234"})
    u = cliente.post("/api/v1/usuarios", json={"nombre": "Solo", "pin": "6666",
                                               "permisos": "vender"})
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": u.json()["id"], "pin": "6666"})
    assert cliente.get("/api/v1/turnos/1/corte").status_code == 403


def test_el_detalle_de_una_venta_anulada_dice_quien_y_cuando(caja, carta):
    v = caja.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}]}).json()
    caja.post(f"/api/v1/ventas/{v['id']}/anular", json={"motivo": "cliente se arrepintió"})
    d = caja.get(f"/api/v1/ventas/{v['id']}").json()
    assert d["estado"] == "anulada" and d["anulada_motivo"] == "cliente se arrepintió"
    assert d["anulada_at"] and "anulada_por" in d
