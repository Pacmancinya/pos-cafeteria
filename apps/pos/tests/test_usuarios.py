"""Usuarios, sesión y presencia.

Lo que se prueba acá no es "el login funciona": es que el login no pueda dejar
al local sin poder cobrar, y que la caja sepa contestar quién abrió, quién
cerró y quién estuvo.
"""
import pytest

from apps.pos import sesion


# ------------------------------------------------------------------ el PIN
def test_el_pin_no_se_guarda_en_claro():
    """`pos.db` se copia a respaldos/ todos los días y esa carpeta termina en
    pendrives. Un PIN legible ahí sería regalarlo."""
    guardado = sesion.cifrar_pin("1234")
    assert "1234" not in guardado
    assert guardado.startswith("pbkdf2_sha256$")
    assert sesion.pin_calza("1234", guardado)
    assert not sesion.pin_calza("1235", guardado)


def test_dos_personas_con_el_mismo_pin_no_comparten_hash():
    """Con sal, dos PIN iguales se ven distintos: nadie puede mirar la tabla y
    decir 'estos dos usan el mismo'."""
    assert sesion.cifrar_pin("1234") != sesion.cifrar_pin("1234")


def test_un_hash_roto_no_deja_entrar_a_nadie():
    for basura in ("", "cualquier cosa", "pbkdf2_sha256$abc", None):
        assert not sesion.pin_calza("1234", basura)


# --------------------------------------------------- la caja nunca se traba
def test_sin_usuarios_la_caja_vende_igual(cliente, carta, caja):
    """La base del local ya está vendiendo y no tiene usuarios. Si esta
    actualización exigiera login, el lunes nadie podría cobrar."""
    assert cliente.get("/api/v1/candado").json()["primer_arranque"] is True
    r = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}]})
    assert r.status_code == 200
    assert cliente.get("/api/v1/sesion").json()["provisorio"] is True


def test_el_primero_es_dueno_aunque_pidan_otra_cosa(cliente):
    """Si el primero pudiera ser cajero, el local quedaría sin nadie capaz de
    crear usuarios."""
    u = cliente.post("/api/v1/usuarios",
                     json={"nombre": "Ruperto", "pin": "1234", "rol": "cajero"}).json()
    assert u["rol"] == "dueno"


def test_con_usuarios_la_puerta_se_cierra(cliente):
    cliente.post("/api/v1/usuarios", json={"nombre": "Ruperto", "pin": "1234"})
    assert cliente.get("/api/v1/sesion").json()["entrado"] is False
    r = cliente.post("/api/v1/usuarios", json={"nombre": "Colado", "pin": "9999"})
    assert r.status_code == 403


def test_el_candado_no_muestra_los_pin(cliente):
    cliente.post("/api/v1/usuarios", json={"nombre": "Ruperto", "pin": "1234"})
    crudo = cliente.get("/api/v1/candado").text
    assert "1234" not in crudo and "pin" not in crudo.lower()


# ------------------------------------------------------------------ entrar
@pytest.fixture()
def dueno(cliente):
    u = cliente.post("/api/v1/usuarios", json={"nombre": "Ruperto", "pin": "1234"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": u["id"], "pin": "1234"})
    return u


def test_entrar_con_el_pin_bueno_y_con_el_malo(cliente, dueno):
    cliente.post("/api/v1/sesion/salir", json={"por": "salir"})
    assert cliente.post("/api/v1/sesion/entrar",
                        json={"usuario_id": dueno["id"], "pin": "0000"}).status_code == 401
    assert cliente.post("/api/v1/sesion/entrar",
                        json={"usuario_id": dueno["id"], "pin": "1234"}).status_code == 200
    assert cliente.get("/api/v1/sesion").json()["nombre"] == "Ruperto"


def test_el_cajero_no_puede_todo(cliente, dueno, carta):
    javi = cliente.post("/api/v1/usuarios",
                        json={"nombre": "Javi", "pin": "4321", "rol": "cajero"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": javi["id"], "pin": "4321"})

    # Abre su caja y vende. El orden importa desde la 2.5: sin caja abierta no
    # se vende, así que primero se abre.
    assert cliente.post("/api/v1/turnos/abrir", json={"cajero": "Javi"}).status_code == 200
    assert cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}]}).status_code == 200
    # ...pero no toca los precios ni la gente.
    assert cliente.post("/api/v1/productos", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "X", "precio": 1}).status_code == 403
    assert cliente.get("/api/v1/usuarios").status_code == 403


def test_el_rol_se_lee_de_la_base_no_de_la_galleta(cliente, dueno, carta):
    """Si al cajero lo ascienden, tiene efecto al toque; si lo bajan, también.
    Una galleta que lleve el rol adentro tardaría horas en enterarse."""
    javi = cliente.post("/api/v1/usuarios",
                        json={"nombre": "Javi", "pin": "4321", "rol": "cajero"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": javi["id"], "pin": "4321"})
    assert cliente.get("/api/v1/usuarios").status_code == 403

    # El dueño lo asciende desde otro equipo; la galleta de Javi no cambia.
    galleta = dict(cliente.cookies)
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": dueno["id"], "pin": "1234"})
    cliente.put(f"/api/v1/usuarios/{javi['id']}",
                json={"nombre": "Javi", "rol": "dueno"})
    cliente.cookies.clear()
    cliente.cookies.update(galleta)
    assert cliente.get("/api/v1/usuarios").status_code == 200


def test_no_se_puede_dejar_el_local_sin_dueno(cliente, dueno):
    assert cliente.delete(f"/api/v1/usuarios/{dueno['id']}").status_code == 409
    assert cliente.put(f"/api/v1/usuarios/{dueno['id']}",
                       json={"nombre": "Ruperto", "rol": "cajero"}).status_code == 409


def test_no_hay_dos_personas_con_el_mismo_nombre(cliente, dueno):
    assert cliente.post("/api/v1/usuarios",
                        json={"nombre": "Ruperto", "pin": "9999"}).status_code == 409


def test_sacar_a_alguien_no_borra_sus_ventas(cliente, dueno, carta, caja):
    javi = cliente.post("/api/v1/usuarios",
                        json={"nombre": "Javi", "pin": "4321", "rol": "cajero"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": javi["id"], "pin": "4321"})
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}]}).json()

    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": dueno["id"], "pin": "1234"})
    assert cliente.delete(f"/api/v1/usuarios/{javi['id']}").status_code == 200
    # La venta sigue ahí y sigue diciendo quién la hizo.
    assert cliente.get(f"/api/v1/ventas/{v['id']}").json()["quien"] == "Javi"
    assert javi["id"] not in [u["id"] for u in cliente.get("/api/v1/candado").json()["usuarios"]]


# ------------------------------------------------------------ quién hizo qué
def test_la_venta_guarda_quien_la_cobro(cliente, dueno, carta, caja):
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}]}).json()
    assert v["usuario_id"] == dueno["id"]
    assert v["quien"] == "Ruperto"


def test_anular_una_caja_ya_cerrada_es_cosa_del_dueno(cliente, dueno, carta):
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Ruperto"})
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"}).json()
    cliente.post("/api/v1/turnos/cerrar", json={"efectivo_contado": 3400})

    javi = cliente.post("/api/v1/usuarios",
                        json={"nombre": "Javi", "pin": "4321", "rol": "cajero"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": javi["id"], "pin": "4321"})
    # Anular una venta de un cuadre que alguien ya firmó no es operación.
    assert cliente.post(f"/api/v1/ventas/{v['id']}/anular",
                        json={"motivo": "no"}).status_code == 403

    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": dueno["id"], "pin": "1234"})
    assert cliente.post(f"/api/v1/ventas/{v['id']}/anular",
                        json={"motivo": "cobrada dos veces"}).status_code == 200


def test_el_turno_dice_quien_abrio_y_quien_cerro(cliente, dueno):
    t = cliente.post("/api/v1/turnos/abrir", json={"cajero": ""}).json()
    assert t["abrio"] == "Ruperto"
    r = cliente.post("/api/v1/turnos/cerrar", json={"efectivo_contado": 0}).json()
    assert r["cerro"] == "Ruperto"


def test_el_turno_dice_quien_estuvo_aunque_no_haya_vendido(cliente, dueno):
    """Este es el requisito original: alguien que atendió dos horas sin cobrar
    nada tiene que aparecer igual."""
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Ruperto"})
    javi = cliente.post("/api/v1/usuarios",
                        json={"nombre": "Javi", "pin": "4321", "rol": "cajero"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": javi["id"], "pin": "4321"})
    cliente.post("/api/v1/sesion/salir", json={"por": "cambio"})
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": dueno["id"], "pin": "1234"})

    t = cliente.get("/api/v1/turnos/actual").json()["turno"]
    estuvieron = {g["nombre"] for g in t["estuvieron"]}
    assert estuvieron == {"Ruperto", "Javi"}     # Javi no vendió nada y aparece igual

    detalle = cliente.get(f"/api/v1/turnos/{t['id']}/presencias").json()
    assert detalle["abrio"] == "Ruperto"
    tramos = [g for g in detalle["estuvieron"] if g["nombre"] == "Javi"][0]["tramos"]
    assert tramos[0]["salida_por"] == "cambio"


def test_una_presencia_olvidada_no_queda_abierta_para_siempre(cliente, dueno):
    """Se corta la luz, se cierra la ventana de golpe. Al volver a entrar, la
    presencia anterior se cierra: si no, diría que trabajó tres días seguidos."""
    for _ in range(3):
        cliente.post("/api/v1/sesion/entrar", json={"usuario_id": dueno["id"], "pin": "1234"})
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Ruperto"})
    t = cliente.get("/api/v1/turnos/actual").json()["turno"]
    assert len(t["estuvieron"]) == 1


# ------------------------------------------------- corte de luz y continuidad
def test_al_reiniciar_el_programa_hay_que_volver_a_marcar_el_pin(cliente, dueno):
    """Si se cortó la luz, el programa no tiene cómo saber si al volver está la
    misma persona frente a la pantalla. Son dos toques y no se pierde nada."""
    from datetime import timedelta

    from apps.pos import sesion
    from core.config import ahora

    assert cliente.get("/api/v1/sesion").json()["entrado"] is True
    original = sesion.ARRANQUE
    try:
        sesion.ARRANQUE = ahora() + timedelta(seconds=1)   # como si acabara de arrancar
        assert cliente.get("/api/v1/sesion").json()["entrado"] is False
    finally:
        sesion.ARRANQUE = original


def test_el_turno_y_las_ventas_sobreviven_al_corte(cliente, dueno, carta):
    """Lo que NO se puede perder: la caja abierta y lo ya cobrado."""
    from datetime import timedelta

    from apps.pos import sesion
    from core.config import ahora

    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Ruperto", "conteo": {"10000": 1}})
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 2}]})

    original = sesion.ARRANQUE
    try:
        sesion.ARRANQUE = ahora() + timedelta(seconds=1)
        # /turnos/actual y la carta no piden sesión: la caja muestra su estado.
        assert cliente.get("/api/v1/turnos/actual").json()["abierto"] is True
        assert len(cliente.get("/api/v1/ventas").json()["ventas"]) == 1
    finally:
        sesion.ARRANQUE = original


def test_una_presencia_que_quedo_abierta_se_cierra_como_corte(cliente, dueno):
    """Sin esto, el turno diría que esa persona estuvo en la caja hasta que
    alguien vuelva a entrar, que pueden ser días."""
    from sqlmodel import Session, select

    from apps.pos.db.models import Presencia
    from apps.pos.db.session import engine
    from apps.pos.sesion import cerrar_presencias_abiertas

    with Session(engine) as s:
        assert cerrar_presencias_abiertas(s, None, "corte") == 1
        p = s.exec(select(Presencia)).first()
        assert p.salio_at is not None and p.salida_por == "corte"


# ------------------------------------------- la caja la cierra quien la abrió
def test_otro_cajero_no_puede_cerrar_la_caja_que_abrio_alguien(cliente, dueno):
    """El cierre es la firma de que el cajón cuadra. Si lo firma alguien que no
    contó el fondo de la mañana, el descuadre queda sin dueño."""
    javi = cliente.post("/api/v1/usuarios",
                        json={"nombre": "Javi", "pin": "4321", "rol": "cajero"}).json()
    ana = cliente.post("/api/v1/usuarios",
                       json={"nombre": "Ana", "pin": "5678", "rol": "cajero"}).json()

    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": javi["id"], "pin": "4321"})
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Javi", "monto_inicial": 10000})

    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": ana["id"], "pin": "5678"})
    r = cliente.post("/api/v1/turnos/cerrar", json={"efectivo_contado": 10000})
    assert r.status_code == 403
    # El mensaje tiene que decir QUÉ HACER, no solo que no se puede: a las diez
    # de la noche un "no tienes permiso" pelado no resuelve nada.
    assert "Javi" in r.json()["detail"]
    assert "dueño" in r.json()["detail"]


def test_el_que_la_abrio_si_la_cierra(cliente, dueno):
    javi = cliente.post("/api/v1/usuarios",
                        json={"nombre": "Javi", "pin": "4321", "rol": "cajero"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": javi["id"], "pin": "4321"})
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Javi"})
    r = cliente.post("/api/v1/turnos/cerrar", json={"efectivo_contado": 0})
    assert r.status_code == 200
    assert r.json()["abrio"] == "Javi" and r.json()["cerro"] == "Javi"


def test_el_dueno_pasa_por_encima_y_queda_escrito(cliente, dueno):
    """El caso real: el cajero se fue a las 19:00 sin cerrar. Una caja abierta
    hasta el día siguiente parte el arqueo en dos jornadas."""
    javi = cliente.post("/api/v1/usuarios",
                        json={"nombre": "Javi", "pin": "4321", "rol": "cajero"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": javi["id"], "pin": "4321"})
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Javi"})

    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": dueno["id"], "pin": "1234"})
    r = cliente.post("/api/v1/turnos/cerrar", json={"efectivo_contado": 0})
    assert r.status_code == 200
    # La excepción no puede ser invisible: tiene que quedar quién cerró.
    assert r.json()["abrio"] == "Javi"
    assert r.json()["cerro"] == "Ruperto"


def test_una_caja_sin_dueno_la_cierra_cualquiera(cliente, dueno):
    """El caso que casi rompe el local: TODOS los turnos de la base real tienen
    `abierto_por_id` NULL —son anteriores a que existieran los usuarios—,
    incluido el que estaba abierto. Una guarda escrita como `!= mi_id` los
    dejaba imposibles de cerrar. NULL significa "no la reclamó nadie".
    """
    from sqlmodel import Session, select

    from apps.pos.db.models import Turno
    from apps.pos.db.session import engine

    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Ruperto"})
    with Session(engine) as s:
        t = s.exec(select(Turno)).first()
        t.abierto_por_id = None          # como los turnos viejos de la base real
        s.add(t)
        s.commit()

    javi = cliente.post("/api/v1/usuarios",
                        json={"nombre": "Javi", "pin": "4321", "rol": "cajero"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": javi["id"], "pin": "4321"})
    assert cliente.post("/api/v1/turnos/cerrar",
                        json={"efectivo_contado": 0}).status_code == 200


def test_si_sacaron_al_que_abrio_la_cierra_el_dueno(cliente, dueno):
    javi = cliente.post("/api/v1/usuarios",
                        json={"nombre": "Javi", "pin": "4321", "rol": "cajero"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": javi["id"], "pin": "4321"})
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Javi"})

    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": dueno["id"], "pin": "1234"})
    cliente.delete(f"/api/v1/usuarios/{javi['id']}")
    r = cliente.post("/api/v1/turnos/cerrar", json={"efectivo_contado": 0})
    assert r.status_code == 200


def test_el_turno_dice_de_quien_es_para_avisar_antes_de_contar(cliente, dueno):
    """La pantalla necesita el ID, no el nombre: dos personas distintas pueden
    llamarse igual si a una la sacaron de la caja."""
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Ruperto"})
    t = cliente.get("/api/v1/turnos/actual").json()["turno"]
    assert t["abierto_por_id"] == dueno["id"]


def test_el_papel_del_cierre_dice_si_lo_cerro_otra_persona(cliente, dueno):
    """La excepción tiene que verse en el papel que se pega en el cuaderno. Si
    solo vive en la base, en el mostrador no existe."""
    javi = cliente.post("/api/v1/usuarios",
                        json={"nombre": "Javi", "pin": "4321", "rol": "cajero"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": javi["id"], "pin": "4321"})
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Javi"})

    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": dueno["id"], "pin": "1234"})
    t = cliente.post("/api/v1/turnos/cerrar", json={"efectivo_contado": 0}).json()

    papel = cliente.get(f"/cierre/{t['id']}").text
    assert "La abrió" in papel and "Javi" in papel
    assert "La cerró" in papel and "Ruperto" in papel


def test_el_papel_no_repite_el_nombre_cuando_cierra_el_mismo(cliente, dueno):
    """Lo normal es que sea la misma persona: ahí una fila 'La cerró' sobra y
    solo hace más largo un papel de 80 mm."""
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Ruperto"})
    t = cliente.post("/api/v1/turnos/cerrar", json={"efectivo_contado": 0}).json()
    assert "La cerró" not in cliente.get(f"/cierre/{t['id']}").text
