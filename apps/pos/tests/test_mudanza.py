"""Pasar una caja instalada con zip a la aplicación (apps/pos/mudanza.py).

Lo que se cuida: que la caja vieja no pierda NADA (ni un byte de su base) y que la nueva
tenga exactamente lo mismo, fila por fila. Las bases viejas de estas pruebas se arman con
datos de varios días y con ventas que todavía están en el -wal (sin pasar al .db), que es
como queda una caja cerrada a la fuerza.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import sys
from datetime import timedelta

import pytest
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from apps.pos import mudanza
from apps.pos.db import models as m
from core.config import ahora


@pytest.fixture(autouse=True)
def _mutex_de_prueba(monkeypatch):
    """Las pruebas jamás tocan el mutex de verdad: una caja abierta en este computador
    no tiene por qué estorbarlas (ni ellas a ella)."""
    monkeypatch.setattr(mudanza, "NOMBRE_MUTEX", f"kofe-prueba-mudanza-{os.getpid()}")
    monkeypatch.setattr(mudanza, "_CORTAR_EN", None)


# ---------------------------------------------------------------------------
# Una caja vieja de mentira, pero con de todo
# ---------------------------------------------------------------------------
def armar_caja_vieja(carpeta, con_wal: bool = True):
    """Crea `carpeta` como una caja instalada con zip. Devuelve el motor que deja el -wal
    sin pasar al .db (hay que cerrarlo con .dispose() al final de la prueba)."""
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "Kofe.exe").write_bytes(b"MZ falso")
    # La versión de la caja vieja que ya trae el bloqueo de la mudanza.
    (carpeta / "apps" / "pos").mkdir(parents=True)
    (carpeta / "apps" / "pos" / "mudanza.py").write_text("# bloqueo\n", encoding="utf-8")
    (carpeta / ".secreto").write_text("a" * 64, encoding="utf-8")
    (carpeta / "respaldos").mkdir()
    (carpeta / "respaldos" / "pos-2026-09-01.db").write_bytes(b"respaldo viejo")
    (carpeta / "registros").mkdir()
    (carpeta / "registros" / "kofe.log").write_text("2026-09-01 INFO todo bien\n", encoding="utf-8")

    motor = create_engine(f"sqlite:///{carpeta / 'pos.db'}",
                          connect_args={"check_same_thread": False})

    @event.listens_for(motor, "connect")
    def _wal(conexion, _):
        c = conexion.cursor()
        c.execute("PRAGMA journal_mode=WAL")
        if con_wal:
            c.execute("PRAGMA wal_autocheckpoint=0")      # nada pasa al .db solo
        c.close()

    SQLModel.metadata.create_all(motor)
    base = ahora()
    with Session(motor) as s:
        cafe = m.Categoria(nombre="Café", orden=0)
        dulce = m.Categoria(nombre="Dulce", orden=1)
        s.add(cafe)
        s.add(dulce)
        s.commit()
        productos = [m.Producto(categoria_id=cafe.id, nombre="Espresso", precio=1900),
                     m.Producto(categoria_id=cafe.id, nombre="Latte", precio=3400, destacado=True),
                     m.Producto(categoria_id=dulce.id, nombre="Alfajor", precio=1900,
                                plu="12", precio_kilo=9990)]
        s.add_all(productos)
        s.commit()
        ana = m.Usuario(nombre="Ana", rol="dueno", pin_hash="pbkdf2_sha256$1$aa$bb", orden=0)
        luis = m.Usuario(nombre="Luis", rol="cajero", pin_hash="pbkdf2_sha256$1$cc$dd", orden=1)
        s.add_all([ana, luis])
        s.commit()
        for clave, valor in (("local_nombre", "Kofe"), ("pin_red", "135790"),
                             ("margen_sugerido", "55"), ("canal_actualizaciones", "piloto"),
                             ("instalacion_id", "abcdef12")):
            s.add(m.Ajuste(clave=clave, valor=valor))
        leche = m.Insumo(nombre="Leche", unidad="ml", stock=8000, minimo=2000, contado=True,
                         formato="Caja 1 L", compra_contenido=1000, compra_costo=1200)
        s.add(leche)
        s.commit()
        s.add(m.Receta(producto_id=productos[1].id, insumo_id=leche.id, cantidad=200))
        s.add(m.CodigoBarra(codigo="7801234567895", producto_id=productos[2].id, cuantos=1))
        numero = 1
        for atras in range(6, -1, -1):
            dia = base - timedelta(days=atras)
            turno = m.Turno(cajero="Ana", abierto_por_id=ana.id, abierto_at=dia,
                            monto_inicial=20000)
            s.add(turno)
            s.commit()
            s.add(m.Presencia(usuario_id=ana.id, turno_id=turno.id, entro_at=dia))
            efectivo = 0
            for k in range(4):
                p = productos[(atras + k) % 3]
                medio = ("efectivo", "debito", "credito", "transferencia")[k]
                v = m.Venta(numero=numero, turno_id=turno.id, total=p.precio * 2, propina=100 * k,
                            medio_pago=medio, creada_at=dia + timedelta(minutes=k), usuario_id=luis.id)
                v.lineas = [m.VentaLinea(producto_id=p.id, nombre=p.nombre,
                                         precio_unitario=p.precio, cantidad=2,
                                         subtotal=p.precio * 2)]
                s.add(v)
                s.commit()
                s.add(m.Pago(venta_id=v.id, medio=medio, monto=p.precio * 2))
                s.add(m.Movimiento(insumo_id=leche.id, tipo="venta", cantidad=-200,
                                   saldo_despues=8000 - 200 * numero, venta_id=v.id,
                                   turno_id=turno.id, hecho_por="Luis"))
                if medio == "efectivo":
                    efectivo += p.precio * 2 + 100 * k
                numero += 1
            s.add(m.RetiroCaja(turno_id=turno.id, monto=3000, motivo="pan", usuario_id=ana.id,
                               hecho_por="Ana"))
            if atras > 0:           # el último día queda con la caja abierta
                turno.efectivo_contado = 20000 + efectivo - 3000
                turno.diferencia = 0
                turno.cerrado_at = dia + timedelta(hours=10)
                turno.cerrado_por_id = ana.id
                s.add(turno)
            s.commit()
            ultimo_turno = turno.id
        id_luis = luis.id
    # Y una venta más que se queda SOLO en el -wal.
    with Session(motor) as s:
        v = m.Venta(numero=numero, turno_id=ultimo_turno, total=7777, medio_pago="efectivo",
                    creada_at=ahora(), usuario_id=id_luis)
        v.lineas = [m.VentaLinea(nombre="Solo en el WAL", precio_unitario=7777, subtotal=7777)]
        s.add(v)
        s.commit()
    return motor


def hash_de(ruta) -> str:
    return hashlib.sha256(open(ruta, "rb").read()).hexdigest()


def foto(carpeta) -> dict:
    """Todos los archivos de la carpeta con su huella, menos el -shm (índice temporal)."""
    salida = {}
    for raiz, _d, nombres in os.walk(carpeta):
        for n in nombres:
            if n.endswith("-shm"):
                continue
            ruta = os.path.join(raiz, n)
            salida[os.path.relpath(ruta, carpeta)] = hash_de(ruta)
    return salida


def volcado(ruta) -> dict:
    c = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        tablas = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name")]
        return {t: c.execute(f'SELECT * FROM "{t}" ORDER BY rowid').fetchall() for t in tablas}
    finally:
        c.close()


def nueva_caja(tmp_path):
    raiz = tmp_path / "nueva"
    raiz.mkdir()
    return raiz, str(raiz / "pos.db")


def pedir(raiz, vieja):
    (raiz / mudanza.ARCHIVO_PEDIDO).write_bytes(str(vieja).encode("utf-8"))


# ---------------------------------------------------------------------------
# La mudanza feliz
# ---------------------------------------------------------------------------
def test_mudanza_trae_todo_igual_y_deja_la_vieja_intacta(tmp_path):
    vieja = tmp_path / "vieja"
    motor = armar_caja_vieja(vieja)
    try:
        assert (vieja / "pos.db-wal").stat().st_size > 0, "la prueba necesita ventas en el WAL"
        antes = foto(vieja)
        raiz, db = nueva_caja(tmp_path)
        pedir(raiz, vieja)

        r = mudanza.ejecutar(str(raiz), db)

        assert r["estado"] == "hecha", r
        # Tablas idénticas, fila por fila (incluida la venta que solo estaba en el WAL).
        nueva, original = volcado(db), volcado(vieja / "pos.db")
        assert nueva == original
        assert any(7777 in f for f in nueva["venta"]), "falta la venta que estaba en el WAL"
        assert r["ventas"] == len(original["venta"]) == 29
        assert r["usuarios"] == 2
        # La base nueva es un archivo solo y sano.
        assert not os.path.exists(db + "-wal")
        c = sqlite3.connect(db)
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        c.close()
        # La caja vieja: mismo contenido de antes, y lo único nuevo es el aviso.
        despues = foto(vieja)
        assert despues.pop(mudanza.MARCA_VIEJA)
        assert despues == antes
        # Lo demás viajó, sin tocar el origen.
        assert (raiz / ".secreto").read_text() == "a" * 64
        assert (raiz / "respaldos" / "pos-2026-09-01.db").read_bytes() == b"respaldo viejo"
        assert (raiz / "registros" / "kofe.log").exists()
        # El respaldo previo existe, abre y es igual.
        previos = [p for p in os.listdir(raiz / "respaldos") if p.startswith("antes-de-mudar-")]
        assert len(previos) == 1
        assert not previos[0].startswith("pos-")      # la poda de respaldos no lo toca
        assert volcado(raiz / "respaldos" / previos[0]) == original
        # Los papeles de la mudanza.
        assert not (raiz / mudanza.ARCHIVO_PEDIDO).exists()
        hecho = json.loads((raiz / mudanza.ARCHIVO_HECHO).read_text(encoding="utf-8"))
        assert hecho["desde"] == str(vieja) and hecho["ventas"] == 29
        assert hecho["filas_por_tabla"]["usuario"] == 2
        marca = (vieja / mudanza.MARCA_VIEJA).read_text(encoding="utf-8-sig")
        assert str(raiz) in marca and "borra SOLO este archivo" in marca
        assert "NO SE BORRO NADA" in marca
        # El aviso se muestra una vez.
        assert mudanza.estado(str(raiz))["estado"] == "hecha"
        assert mudanza.estado(str(raiz))["aviso_visto"] is False
        mudanza.marcar_visto(str(raiz))
        assert mudanza.estado(str(raiz))["aviso_visto"] is True
        # Segunda ejecución: no hay nada que hacer, nada se repite.
        assert mudanza.ejecutar(str(raiz), db) is None
        assert volcado(db) == original
    finally:
        motor.dispose()


def test_mudanza_sin_el_indice_shm_tambien_lee_el_wal(tmp_path):
    """Una caja cerrada a la fuerza y copiada: quedan el .db y el -wal, sin -shm."""
    origen = tmp_path / "origen"
    motor = armar_caja_vieja(origen)
    try:
        vieja = tmp_path / "vieja"
        shutil.copytree(origen, vieja, ignore=shutil.ignore_patterns("*-shm"))
        assert not (vieja / "pos.db-shm").exists() and (vieja / "pos.db-wal").stat().st_size > 0
    finally:
        motor.dispose()
    raiz, db = nueva_caja(tmp_path)
    pedir(raiz, vieja)
    antes_db, antes_wal = hash_de(vieja / "pos.db"), hash_de(vieja / "pos.db-wal")
    r = mudanza.ejecutar(str(raiz), db)
    assert r["estado"] == "hecha", r
    assert r["ventas"] == 29
    assert hash_de(vieja / "pos.db") == antes_db
    assert hash_de(vieja / "pos.db-wal") == antes_wal


# ---------------------------------------------------------------------------
# Lo que no se hace
# ---------------------------------------------------------------------------
def test_si_la_base_nueva_tiene_datos_no_se_pisa(tmp_path):
    vieja = tmp_path / "vieja"
    motor = armar_caja_vieja(vieja)
    try:
        raiz, db = nueva_caja(tmp_path)
        propia = create_engine(f"sqlite:///{db}")
        SQLModel.metadata.create_all(propia)
        with Session(propia) as s:
            s.add(m.Usuario(nombre="Nueva", pin_hash="x"))
            s.commit()
        propia.dispose()
        propio = hash_de(db)
        antes = foto(vieja)
        pedir(raiz, vieja)

        r = mudanza.ejecutar(str(raiz), db)

        assert r["estado"] == "no_hecha"
        assert hash_de(db) == propio
        assert foto(vieja) == antes                       # ni siquiera el aviso
        assert not (raiz / mudanza.ARCHIVO_PEDIDO).exists()
        e = mudanza.estado(str(raiz))
        assert e["estado"] == "no_hecha" and "no se trajo nada" in e["motivo"].lower()
        assert mudanza.ejecutar(str(raiz), db) is None
    finally:
        motor.dispose()


def test_una_base_nueva_recien_creada_si_se_reemplaza(tmp_path):
    vieja = tmp_path / "vieja"
    motor = armar_caja_vieja(vieja)
    try:
        raiz, db = nueva_caja(tmp_path)
        vacia = create_engine(f"sqlite:///{db}")
        SQLModel.metadata.create_all(vacia)
        vacia.dispose()
        pedir(raiz, vieja)
        r = mudanza.ejecutar(str(raiz), db)
        assert r["estado"] == "hecha", r
        assert volcado(db) == volcado(vieja / "pos.db")
        # La vacía no se perdió: quedó aparte.
        assert [p for p in os.listdir(raiz) if p.startswith("pos.db.vacia-antes-de-mudar-")]
    finally:
        motor.dispose()


def test_base_vieja_corrupta_no_deja_base_a_medias(tmp_path):
    vieja = tmp_path / "vieja"
    vieja.mkdir()
    (vieja / "Kofe.exe").write_bytes(b"x")
    (vieja / "pos.db").write_bytes(b"esto no es una base de datos" * 200)
    antes = foto(vieja)
    raiz, db = nueva_caja(tmp_path)
    pedir(raiz, vieja)

    r = mudanza.ejecutar(str(raiz), db)

    assert r["estado"] == "error"
    assert not os.path.exists(db) and not os.path.exists(db + ".mudando")
    assert (raiz / mudanza.ARCHIVO_PEDIDO).exists()          # queda para reintentar
    assert foto(vieja) == antes
    e = mudanza.estado(str(raiz))
    assert e["estado"] == "error" and e["mensaje"]
    assert not (vieja / mudanza.MARCA_VIEJA).exists()


@pytest.mark.parametrize("caso", ["sin_carpeta", "sin_base", "pedido_vacio", "es_la_misma"])
def test_pedido_imposible_queda_pendiente_con_aviso(tmp_path, caso):
    raiz, db = nueva_caja(tmp_path)
    if caso == "sin_carpeta":
        pedir(raiz, tmp_path / "no-existe")
    elif caso == "sin_base":
        (tmp_path / "v").mkdir()
        pedir(raiz, tmp_path / "v")
    elif caso == "pedido_vacio":
        pedir(raiz, "")
    else:
        pedir(raiz, raiz)
    r = mudanza.ejecutar(str(raiz), db)
    assert r["estado"] == "error" and r["mensaje"]
    assert not os.path.exists(db)
    assert (raiz / mudanza.ARCHIVO_PEDIDO).exists()
    assert mudanza.estado(str(raiz))["estado"] == "error"


def test_si_el_respaldo_previo_falla_no_se_muda_nada(tmp_path, monkeypatch):
    vieja = tmp_path / "vieja"
    motor = armar_caja_vieja(vieja)
    try:
        raiz, db = nueva_caja(tmp_path)
        pedir(raiz, vieja)
        antes = foto(vieja)

        def falla(origen, destino):
            raise sqlite3.OperationalError("disco lleno")
        monkeypatch.setattr(mudanza, "_copiar_base", falla)
        r = mudanza.ejecutar(str(raiz), db)

        assert r["estado"] == "error" and "respaldo previo" in r["mensaje"]
        assert not os.path.exists(db)
        assert foto(vieja) == antes
    finally:
        motor.dispose()


def test_si_una_tabla_difiere_la_mudanza_falla_y_se_descarta_el_temporal(tmp_path, monkeypatch):
    vieja = tmp_path / "vieja"
    motor = armar_caja_vieja(vieja)
    try:
        raiz, db = nueva_caja(tmp_path)
        pedir(raiz, vieja)
        original = mudanza._copiar_base
        llamadas = []

        def copia_con_una_fila_menos(origen, destino):
            original(origen, destino)
            llamadas.append(destino)
            if destino.endswith(".mudando"):          # solo la base nueva sale mal
                c = sqlite3.connect(destino)
                c.execute("DELETE FROM ajuste WHERE clave='margen_sugerido'")
                c.commit()
                c.close()
        monkeypatch.setattr(mudanza, "_copiar_base", copia_con_una_fila_menos)
        antes = foto(vieja)

        r = mudanza.ejecutar(str(raiz), db)

        assert r["estado"] == "error" and "ajuste" in r["mensaje"]
        assert len(llamadas) == 2
        assert not os.path.exists(db) and not os.path.exists(db + ".mudando")
        assert (raiz / mudanza.ARCHIVO_PEDIDO).exists()
        assert foto(vieja) == antes
        assert not (vieja / mudanza.MARCA_VIEJA).exists()
    finally:
        motor.dispose()


# ---------------------------------------------------------------------------
# La caja vieja ya no vende
# ---------------------------------------------------------------------------
def test_la_carpeta_vieja_no_vende_y_se_arregla_borrando_la_marca(cliente, tmp_path, monkeypatch):
    monkeypatch.setattr(mudanza, "RAIZ", str(tmp_path))
    assert cliente.get("/api/v1/salud").status_code == 200       # normal
    (tmp_path / mudanza.MARCA_VIEJA).write_text("se mudó", encoding="utf-8")

    pagina = cliente.get("/")
    assert pagina.status_code == 200 and "Esta caja se mudó" in pagina.text
    assert "ESTA-CAJA-SE-MUDO.txt" in pagina.text            # la salida de emergencia
    for ruta in ("/pantallas", "/static/app.js", "/entrar"):
        assert "Esta caja se mudó" in cliente.get(ruta).text, ruta
    # Nada de la API responde: ni leer ni vender ni actualizar.
    for metodo, ruta in (("get", "/api/v1/salud"), ("get", "/api/v1/carta"),
                         ("get", "/api/v1/turnos/actual"), ("post", "/api/v1/ventas"),
                         ("post", "/api/v1/turnos/abrir"), ("post", "/api/v1/actualizacion"),
                         ("get", "/api/v1/actualizacion")):
        r = getattr(cliente, metodo)(ruta, **({"json": {}} if metodo == "post" else {}))
        assert r.status_code == 410, (ruta, r.status_code)
        assert "se mudó" in r.json()["detail"]

    # Salida de emergencia: sin el archivo, todo vuelve a funcionar.
    (tmp_path / mudanza.MARCA_VIEJA).unlink()
    assert cliente.get("/api/v1/salud").status_code == 200
    assert "Esta caja se mudó" not in cliente.get("/").text


def test_el_actualizador_de_la_carpeta_vieja_no_funciona(tmp_path, monkeypatch):
    from apps.pos import actualizar
    monkeypatch.setattr(mudanza, "RAIZ", str(tmp_path))
    (tmp_path / mudanza.MARCA_VIEJA).write_text("x", encoding="utf-8")
    assert "se mudó" in actualizar.revisar()["error"]
    assert "se mudó" in actualizar.aplicar("https://ejemplo.cl/p.zip")["error"]


def test_el_aviso_de_mudanza_por_la_api(cliente, tmp_path, monkeypatch):
    monkeypatch.setattr(mudanza, "RAIZ", str(tmp_path))
    assert cliente.get("/api/v1/mudanza").json()["estado"] == "ninguna"
    (tmp_path / mudanza.ARCHIVO_HECHO).write_text(
        json.dumps({"desde": "C:\\Kofe", "fecha": "2026-10-08T10:00:00", "ventas": 5,
                    "usuarios": 2, "aviso_visto": False}), encoding="utf-8")
    d = cliente.get("/api/v1/mudanza").json()
    assert d["estado"] == "hecha" and d["desde"] == "C:\\Kofe" and d["aviso_visto"] is False
    assert cliente.post("/api/v1/mudanza/visto").json()["ok"] is True
    assert cliente.get("/api/v1/mudanza").json()["aviso_visto"] is True


# ---------------------------------------------------------------------------
# Refuerzos de la revisión: versión de la vieja, exclusión, orden, fases, bloqueo
# ---------------------------------------------------------------------------
class Corte(BaseException):
    """Un corte de luz: no lo atrapa ningún `except Exception`, nada se limpia."""


def libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def preparar(tmp_path, **kw):
    vieja = tmp_path / "vieja"
    motor = armar_caja_vieja(vieja, **kw)
    raiz, db = nueva_caja(tmp_path)
    pedir(raiz, vieja)
    return vieja, motor, raiz, db


def termina_bien(raiz, db, vieja, antes):
    """La mudanza se retoma y termina, idéntica fila por fila, con la vieja intacta."""
    r = mudanza.ejecutar(str(raiz), db)
    assert r["estado"] == "hecha" and r["completo"] is True, r
    assert volcado(db) == volcado(vieja / "pos.db")
    assert not (raiz / mudanza.ARCHIVO_PEDIDO).exists()
    assert (raiz / mudanza.ARCHIVO_HECHO).exists()
    despues = foto(vieja)
    assert despues.pop(mudanza.MARCA_VIEJA)
    assert despues == antes
    assert mudanza.ejecutar(str(raiz), db) is None


def test_no_se_muda_desde_una_caja_vieja_sin_el_bloqueo(tmp_path):
    vieja, motor, raiz, db = preparar(tmp_path)
    try:
        os.remove(vieja / "apps" / "pos" / "mudanza.py")
        antes = foto(vieja)
        r = mudanza.ejecutar(str(raiz), db)
        assert r["estado"] == "error" and r["tipo"] == "version"
        assert "Primero abre la caja vieja" in r["mensaje"]
        assert foto(vieja) == antes and not os.path.exists(db)
        assert mudanza.pendiente(str(raiz))
    finally:
        motor.dispose()


def test_con_el_puerto_ocupado_no_se_muda(tmp_path):
    vieja, motor, raiz, db = preparar(tmp_path)
    try:
        antes = foto(vieja)
        with socket.socket() as ocupante:
            ocupante.bind(("0.0.0.0", 0))
            ocupante.listen()
            puerto = ocupante.getsockname()[1]
            r = mudanza.ejecutar(str(raiz), db, puerto=puerto)
        assert r["estado"] == "error" and r["tipo"] == "vieja_abierta"
        assert foto(vieja) == antes and not os.path.exists(db)        # ni siquiera la marca
        # Con el puerto libre, sigue y termina.
        r = mudanza.ejecutar(str(raiz), db, puerto=libre())
        assert r["estado"] == "hecha"
    finally:
        motor.dispose()


@pytest.mark.skipif(sys.platform != "win32", reason="el mutex es de Windows")
def test_con_el_mutex_ocupado_no_se_muda_y_se_suelta_al_terminar(tmp_path):
    vieja, motor, raiz, db = preparar(tmp_path)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    try:
        antes = foto(vieja)
        ocupante = k32.CreateMutexW(None, False, mudanza.NOMBRE_MUTEX)
        try:
            r = mudanza.ejecutar(str(raiz), db, puerto=libre())
        finally:
            k32.CloseHandle(ocupante)
        assert r["estado"] == "error" and r["tipo"] == "vieja_abierta"
        assert foto(vieja) == antes and not os.path.exists(db)
        assert mudanza.ejecutar(str(raiz), db, puerto=libre())["estado"] == "hecha"
        # Terminada la mudanza el mutex quedó libre: se puede tomar de nuevo.
        k32.SetLastError(0)
        h = k32.CreateMutexW(None, False, mudanza.NOMBRE_MUTEX)
        assert ctypes.get_last_error() != 183 and ctypes.windll.kernel32.GetLastError() != 183
        k32.CloseHandle(h)
    finally:
        motor.dispose()


def test_la_marca_va_primero_y_si_falla_la_vieja_vuelve_a_funcionar(tmp_path, monkeypatch):
    vieja, motor, raiz, db = preparar(tmp_path)
    try:
        antes = foto(vieja)
        vistas = []
        original = mudanza._copiar_base

        def espia(origen, destino):
            vistas.append((destino, (vieja / mudanza.MARCA_VIEJA).exists()))
            if destino.endswith(".mudando"):
                raise sqlite3.OperationalError("disco lleno")
            original(origen, destino)
        monkeypatch.setattr(mudanza, "_copiar_base", espia)

        r = mudanza.ejecutar(str(raiz), db)

        # El respaldo y el temporal se sacaron con la vieja YA bloqueada.
        assert vistas and all(marca for _, marca in vistas)
        assert r["estado"] == "error"
        # Y como falló antes de instalar, la vieja volvió a funcionar y todo se descartó.
        assert foto(vieja) == antes
        assert not os.path.exists(db) and not os.path.exists(db + ".mudando")
        assert not (raiz / mudanza.ARCHIVO_ESTADO).exists()
        assert (raiz / mudanza.ARCHIVO_PEDIDO).exists() and mudanza.pendiente(str(raiz))
        monkeypatch.setattr(mudanza, "_copiar_base", original)
        termina_bien(raiz, db, vieja, antes)
    finally:
        motor.dispose()


@pytest.mark.parametrize("fase", ["marca", "respaldo", "verificada"])
def test_un_error_antes_de_instalar_deshace_y_se_reintenta(tmp_path, monkeypatch, fase):
    vieja, motor, raiz, db = preparar(tmp_path)
    try:
        antes = foto(vieja)
        monkeypatch.setattr(mudanza, "_CORTAR_EN", fase)
        r = mudanza.ejecutar(str(raiz), db)
        assert r["estado"] == "error"
        assert foto(vieja) == antes                       # la vieja, sin marca
        assert not os.path.exists(db) and mudanza.pendiente(str(raiz))
        monkeypatch.setattr(mudanza, "_CORTAR_EN", None)
        termina_bien(raiz, db, vieja, antes)
    finally:
        motor.dispose()


@pytest.mark.parametrize("fase", ["marca", "respaldo", "verificada"])
def test_un_corte_de_luz_antes_de_instalar_se_retoma(tmp_path, monkeypatch, fase):
    vieja, motor, raiz, db = preparar(tmp_path)
    try:
        antes = foto(vieja)

        def corte(nombre):
            if nombre == fase:
                raise Corte()
        monkeypatch.setattr(mudanza, "_punto", corte)
        with pytest.raises(Corte):
            mudanza.ejecutar(str(raiz), db)
        # Quedó a medias: la vieja marcada, el estado en esa fase, la caja nueva sin abrir.
        assert (vieja / mudanza.MARCA_VIEJA).exists()
        st = json.loads((raiz / mudanza.ARCHIVO_ESTADO).read_text(encoding="utf-8"))
        assert st["fase"] == fase
        assert mudanza.pendiente(str(raiz)) and not os.path.exists(db)
        monkeypatch.setattr(mudanza, "_punto", lambda _n: None)
        termina_bien(raiz, db, vieja, antes)
    finally:
        motor.dispose()


@pytest.mark.parametrize("fase", ["instalada", "auxiliares"])
def test_un_corte_despues_de_instalar_la_base_termina_sin_tomarla_por_datos_propios(
        tmp_path, monkeypatch, fase):
    vieja, motor, raiz, db = preparar(tmp_path)
    try:
        antes = foto(vieja)

        def corte(nombre):
            if nombre == fase:
                raise Corte()
        monkeypatch.setattr(mudanza, "_punto", corte)
        with pytest.raises(Corte):
            mudanza.ejecutar(str(raiz), db)
        # La base ya es la copia; el pedido sigue hasta que todo termine.
        assert (raiz / mudanza.ARCHIVO_PEDIDO).exists() and os.path.exists(db)
        assert not mudanza.pendiente(str(raiz))
        assert mudanza.estado(str(raiz))["completo"] is False
        monkeypatch.setattr(mudanza, "_punto", lambda _n: None)
        termina_bien(raiz, db, vieja, antes)
    finally:
        motor.dispose()


def test_un_corte_justo_despues_de_reemplazar_la_base_reconoce_la_copia(tmp_path, monkeypatch):
    """pos.db ya es la copia (con ventas y usuarios) pero el estado aún dice «verificada»."""
    vieja, motor, raiz, db = preparar(tmp_path)
    try:
        antes = foto(vieja)
        original = mudanza._guardar_estado

        def guardar(r, st):
            if st.get("fase") == "instalada":
                raise Corte()
            original(r, st)
        monkeypatch.setattr(mudanza, "_guardar_estado", guardar)
        with pytest.raises(Corte):
            mudanza.ejecutar(str(raiz), db)
        assert os.path.exists(db)
        st = json.loads((raiz / mudanza.ARCHIVO_ESTADO).read_text(encoding="utf-8"))
        assert st["fase"] == "verificada"
        monkeypatch.setattr(mudanza, "_guardar_estado", original)
        termina_bien(raiz, db, vieja, antes)           # «hecha», no «no_hecha»
    finally:
        motor.dispose()


def test_con_la_instalacion_confirmada_reintentar_no_compara_ni_toca_la_base(tmp_path, monkeypatch):
    """La caja ya vendió: reintentar la copia retoma solo los auxiliares y el cierre."""
    vieja, motor, raiz, db = preparar(tmp_path)
    try:
        antes = foto(vieja)
        original = shutil.copy2

        def copia_que_falla(o, d, *a, **k):
            if str(o).endswith("kofe.log"):
                raise OSError("sin permiso")
            return original(o, d, *a, **k)
        monkeypatch.setattr(mudanza.shutil, "copy2", copia_que_falla)
        r = mudanza.ejecutar(str(raiz), db)
        assert r["estado"] == "hecha" and r["completo"] is False

        # La caja nueva vende (su base ya no es igual a la importada).
        c = sqlite3.connect(db)
        c.execute("INSERT INTO ajuste (clave, valor) VALUES ('vendio_hoy', '1')")
        c.commit()
        c.close()
        vendida = hash_de(db)

        monkeypatch.setattr(mudanza.shutil, "copy2", original)
        r = mudanza.ejecutar(str(raiz), db)

        assert r["estado"] == "hecha" and r["completo"] is True, r
        assert hash_de(db) == vendida                                   # intacta
        assert (raiz / "registros" / "kofe.log").exists()
        assert not (raiz / mudanza.ARCHIVO_PEDIDO).exists()
        despues = foto(vieja)
        despues.pop(mudanza.MARCA_VIEJA)
        assert despues == antes
    finally:
        motor.dispose()


def test_si_faltan_auxiliares_se_dice_cuales_y_no_se_da_por_terminada(tmp_path, monkeypatch):
    vieja, motor, raiz, db = preparar(tmp_path)
    try:
        antes = foto(vieja)
        original = shutil.copy2

        def copia_que_falla(o, d, *a, **k):
            if str(o).endswith("kofe.log"):
                raise OSError("sin permiso")
            return original(o, d, *a, **k)
        monkeypatch.setattr(mudanza.shutil, "copy2", copia_que_falla)

        r = mudanza.ejecutar(str(raiz), db)

        assert r["estado"] == "hecha" and r["completo"] is False
        assert any("kofe.log" in f for f in r["faltan"])
        assert (raiz / mudanza.ARCHIVO_PEDIDO).exists()                  # no se borra todavía
        assert not (raiz / mudanza.ARCHIVO_HECHO).exists()
        assert not mudanza.pendiente(str(raiz))                          # la caja abre
        e = mudanza.estado(str(raiz))
        assert e["estado"] == "hecha" and e["completo"] is False and e["faltan"]
        assert volcado(db) == volcado(vieja / "pos.db")
        # «Reintentar copia»: ahora sí.
        monkeypatch.setattr(mudanza.shutil, "copy2", original)
        r = mudanza.ejecutar(str(raiz), db)
        assert r["completo"] is True
        assert (raiz / "registros" / "kofe.log").exists()
        assert mudanza.estado(str(raiz))["completo"] is True
        despues = foto(vieja)
        despues.pop(mudanza.MARCA_VIEJA)
        assert despues == antes
    finally:
        motor.dispose()


def test_una_copia_auxiliar_que_no_coincide_cuenta_como_faltante(tmp_path, monkeypatch):
    vieja, motor, raiz, db = preparar(tmp_path)
    try:
        original = shutil.copy2

        def copia_corrupta(o, d, *a, **k):
            r = original(o, d, *a, **k)
            if str(o).endswith("pos-2026-09-01.db"):
                with open(d, "ab") as f:
                    f.write(b"basura")
            return r
        monkeypatch.setattr(mudanza.shutil, "copy2", copia_corrupta)
        r = mudanza.ejecutar(str(raiz), db)
        assert r["completo"] is False and any("pos-2026-09-01.db" in f for f in r["faltan"])
        assert not (raiz / "respaldos" / "pos-2026-09-01.db").exists()   # no queda una copia mala
    finally:
        motor.dispose()


# ---------------------------------------------------------------------------
# Pendiente = la caja no abre
# ---------------------------------------------------------------------------
def test_con_una_mudanza_pendiente_la_caja_no_deja_hacer_nada(cliente, tmp_path, monkeypatch):
    monkeypatch.setattr(mudanza, "RAIZ", str(tmp_path))
    monkeypatch.setattr(mudanza, "_ruta_base_nueva", lambda: str(tmp_path / "pos.db"))
    vieja = tmp_path / "vieja"
    motor = armar_caja_vieja(vieja)
    try:
        os.remove(vieja / "apps" / "pos" / "mudanza.py")      # fuerza el error «version»
        pedir(tmp_path, vieja)
        mudanza.ejecutar(str(tmp_path), str(tmp_path / "pos.db"))
        assert mudanza.pendiente()

        pagina = cliente.get("/")
        assert pagina.status_code == 200
        assert "Reintentar" in pagina.text and "no traer nada" in pagina.text
        assert "Primero abre la caja vieja" in pagina.text           # el error, en palabras simples
        assert "Reintentar" in cliente.get("/entrar").text
        for metodo, ruta in (("post", "/api/v1/ventas"), ("post", "/api/v1/usuarios"),
                             ("post", "/api/v1/turnos/abrir"), ("get", "/api/v1/carta"),
                             ("post", "/api/v1/local")):
            r = getattr(cliente, metodo)(ruta, **({"json": {}} if metodo == "post" else {}))
            assert r.status_code == 423, (ruta, r.status_code)
        e = cliente.get("/api/v1/mudanza").json()
        assert e["estado"] == "error" and e["bloquea"] is True and e["tipo"] == "version"
        # Reintentar con el mismo problema: sigue pendiente, sin tocar la base.
        assert cliente.post("/api/v1/mudanza/reintentar").json()["estado"] == "error"
        assert mudanza.pendiente()

        # «Esta caja es nueva»: pide confirmación...
        assert cliente.post("/api/v1/mudanza/descartar", json={}).status_code == 422
        assert mudanza.pendiente()
        # ...y con ella se descarta, la vieja queda sin marca y la caja abre normal.
        antes = foto(vieja)
        assert cliente.post("/api/v1/mudanza/descartar", json={"confirmar": True}).json()["ok"]
        assert not mudanza.pendiente() and foto(vieja) == antes
        assert not (tmp_path / mudanza.ARCHIVO_PEDIDO).exists()
        assert "Reintentar" not in cliente.get("/").text
        assert cliente.get("/api/v1/salud").status_code == 200
    finally:
        motor.dispose()


def test_descartar_quita_la_marca_que_puso_la_mudanza(tmp_path, monkeypatch):
    vieja, motor, raiz, db = preparar(tmp_path)
    try:
        antes = foto(vieja)
        monkeypatch.setattr(mudanza, "_punto", lambda n: (_ for _ in ()).throw(Corte())
                            if n == "respaldo" else None)
        with pytest.raises(Corte):
            mudanza.ejecutar(str(raiz), db)
        assert (vieja / mudanza.MARCA_VIEJA).exists()
        assert mudanza.descartar(str(raiz))["ok"]
        assert foto(vieja) == antes and not mudanza.pendiente(str(raiz))
        assert not (raiz / mudanza.ARCHIVO_ESTADO).exists()
    finally:
        motor.dispose()


def test_descartar_no_vale_una_vez_instalada_la_base(tmp_path, monkeypatch):
    vieja, motor, raiz, db = preparar(tmp_path)
    try:
        monkeypatch.setattr(mudanza, "_CORTAR_EN", "instalada")
        mudanza.ejecutar(str(raiz), db)
        assert mudanza.descartar(str(raiz))["ok"] is False
        assert (raiz / mudanza.ARCHIVO_PEDIDO).exists() and os.path.exists(db)
    finally:
        motor.dispose()


def test_el_estado_se_escribe_de_forma_atomica(tmp_path):
    mudanza._guardar_estado(str(tmp_path), {"fase": "marca"})
    assert json.loads((tmp_path / mudanza.ARCHIVO_ESTADO).read_text(encoding="utf-8")) == {
        "fase": "marca"}
    assert not (tmp_path / (mudanza.ARCHIVO_ESTADO + ".tmp")).exists()

# ---------------------------------------------------------------------------
# Segunda pasada de la revisión
# ---------------------------------------------------------------------------
def test_reintentar_y_descartar_no_corren_a_la_vez(tmp_path, monkeypatch):
    import threading
    from types import SimpleNamespace

    from fastapi import HTTPException

    from apps.pos.api import mudanza as api
    raiz, db = nueva_caja(tmp_path)
    (raiz / mudanza.ARCHIVO_PEDIDO).write_text("C:\\no-importa", encoding="utf-8")
    monkeypatch.setattr(mudanza, "RAIZ", str(raiz))
    adentro, soltar = threading.Event(), threading.Event()

    def lenta(*_a, **_k):
        adentro.set()
        assert soltar.wait(10)
        return {"estado": "error"}
    monkeypatch.setattr(mudanza, "_mudar", lenta)
    monkeypatch.setattr(api, "_soltar_la_base", lambda: None)
    monkeypatch.setattr(api, "_abrir_la_base_si_corresponde", lambda: None)
    peticion = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    resultados = {}
    hilo = threading.Thread(target=lambda: resultados.update(a=api.reintentar()))
    hilo.start()
    try:
        assert adentro.wait(10)
        for llamada in (lambda: api.descartar(api.DescartarIn(confirmar=True), peticion),
                        api.reintentar):
            with pytest.raises(HTTPException) as e:
                llamada()
            assert e.value.status_code == 409 and "mudanza en curso" in e.value.detail
        # Y mientras dura, la caja sigue bloqueada (423).
        assert mudanza.pendiente(str(raiz))
    finally:
        soltar.set()
        hilo.join(10)
    assert "a" in resultados
    # Terminada la primera, el bloqueo queda libre.
    with mudanza.operacion():
        pass


def test_antes_de_reemplazar_se_vuelve_a_mirar_el_destino(tmp_path, monkeypatch):
    vieja, motor, raiz, db = preparar(tmp_path)
    try:
        antes = foto(vieja)

        def alguien_vende(nombre):
            if nombre == "verificada":
                propia = create_engine(f"sqlite:///{db}")
                SQLModel.metadata.create_all(propia)
                with Session(propia) as s:
                    s.add(m.Usuario(nombre="Colado", pin_hash="x"))
                    s.commit()
                propia.dispose()
        monkeypatch.setattr(mudanza, "_punto", alguien_vende)
        r = mudanza.ejecutar(str(raiz), db)
        assert r["estado"] == "error" and "datos propios" in r["mensaje"]
        assert foto(vieja) == antes                              # la vieja, sin marca
        c = sqlite3.connect(db)
        assert c.execute("SELECT nombre FROM usuario").fetchall() == [("Colado",)]   # no se pisó
        c.close()
    finally:
        motor.dispose()


def test_si_no_se_guardo_la_fase_instalada_no_se_puede_descartar_y_reintentar_termina(
        tmp_path, monkeypatch):
    vieja, motor, raiz, db = preparar(tmp_path)
    try:
        antes = foto(vieja)
        original = mudanza._guardar_estado

        def guardar(r, st):
            if st.get("fase") == "instalada":
                raise OSError("disco lleno")
            original(r, st)
        monkeypatch.setattr(mudanza, "_guardar_estado", guardar)
        r = mudanza.ejecutar(str(raiz), db)
        assert r["estado"] == "error"
        assert os.path.exists(db) and (vieja / mudanza.MARCA_VIEJA).exists()
        assert mudanza.pendiente(str(raiz))                    # el estado aún dice «verificada»

        # Descartar dejaría dos cajas con el mismo historial: se rechaza.
        d = mudanza.descartar(str(raiz), db)
        assert d["ok"] is False and "Reintentar" in d["detalle"]
        assert (vieja / mudanza.MARCA_VIEJA).exists() and os.path.exists(db)
        assert (raiz / mudanza.ARCHIVO_PEDIDO).exists()

        monkeypatch.setattr(mudanza, "_guardar_estado", original)
        termina_bien(raiz, db, vieja, antes)
    finally:
        motor.dispose()


def test_descartar_ante_la_duda_se_rechaza(tmp_path):
    vieja, motor, raiz, db = preparar(tmp_path)
    try:
        # Estado a medias y una base ilegible: no se sabe de quién es, no se descarta.
        mudanza._guardar_estado(str(raiz), {"desde": str(vieja), "marca_escrita": True,
                                            "fase": "marca"})
        (vieja / mudanza.MARCA_VIEJA).write_text("x", encoding="utf-8")
        open(db, "wb").write(b"no es una base" * 100)
        d = mudanza.descartar(str(raiz), db)
        assert d["ok"] is False
        assert (vieja / mudanza.MARCA_VIEJA).exists()
    finally:
        motor.dispose()


def test_un_auxiliar_cortado_a_la_mitad_se_detecta_y_se_recopia(tmp_path):
    vieja, motor, raiz, db = preparar(tmp_path)
    try:
        (raiz / "respaldos").mkdir()
        # Una copia nuestra que se cortó: el comienzo exacto del original.
        (raiz / "respaldos" / "pos-2026-09-01.db").write_bytes(b"respal")
        # Y un temporal que quedó de un corte anterior.
        (raiz / "registros").mkdir()
        (raiz / "registros" / "kofe.log.copiando").write_bytes(b"basura a medias")
        r = mudanza.ejecutar(str(raiz), db)
        assert r["completo"] is True, r
        assert (raiz / "respaldos" / "pos-2026-09-01.db").read_bytes() == b"respaldo viejo"
        assert not [p for p in os.listdir(raiz / "respaldos") if p.endswith(mudanza.SUFIJO_COPIA)]
        assert (raiz / "registros" / "kofe.log").read_text(encoding="utf-8").startswith("2026-09-01")
        assert not (raiz / "registros" / "kofe.log.copiando").exists()
    finally:
        motor.dispose()


def test_un_auxiliar_preexistente_distinto_se_conserva_y_se_agrega_la_copia_sufijada(tmp_path):
    vieja, motor, raiz, db = preparar(tmp_path)
    try:
        (raiz / "registros").mkdir()
        (raiz / "registros" / "kofe.log").write_text("log de la caja nueva\n", encoding="utf-8")
        (raiz / ".secreto").write_text("otro-secreto", encoding="utf-8")
        r = mudanza.ejecutar(str(raiz), db)
        assert r["completo"] is True, r
        assert (raiz / "registros" / "kofe.log").read_text(encoding="utf-8") == "log de la caja nueva\n"
        assert (raiz / "registros" / ("kofe.log" + mudanza.SUFIJO_COPIA)).read_text(
            encoding="utf-8") == "2026-09-01 INFO todo bien\n"
        assert (raiz / ".secreto").read_text() == "otro-secreto"            # no se pisa
        assert (raiz / (".secreto" + mudanza.SUFIJO_COPIA)).read_text() == "a" * 64
    finally:
        motor.dispose()


def test_un_auxiliar_no_verificado_cuenta_como_faltante_y_nunca_deja_un_destino_a_medias(
        tmp_path, monkeypatch):
    vieja, motor, raiz, db = preparar(tmp_path)
    try:
        original = shutil.copy2

        def corta(o, d, *a, **k):
            r = original(o, d, *a, **k)
            if str(o).endswith("kofe.log"):
                with open(d, "r+b") as f:
                    f.truncate(5)                    # se cortó a la mitad
            return r
        monkeypatch.setattr(mudanza.shutil, "copy2", corta)
        r = mudanza.ejecutar(str(raiz), db)
        assert r["completo"] is False and any("kofe.log" in f for f in r["faltan"])
        assert not (raiz / "registros" / "kofe.log").exists()          # el destino, intacto
        assert not (raiz / "registros" / "kofe.log.copiando").exists()
        monkeypatch.setattr(mudanza.shutil, "copy2", original)
        assert mudanza.ejecutar(str(raiz), db)["completo"] is True
    finally:
        motor.dispose()


def test_colision_doble_no_pisa_el_archivo_sufijado(tmp_path):
    """Si el destino y su `.desde-caja-vieja` ya existen y son otra cosa, la copia va a
    un nombre libre: ninguno de los dos se reemplaza."""
    vieja, nueva = tmp_path / "vieja", tmp_path / "nueva"
    vieja.mkdir(); nueva.mkdir()
    (vieja / "r.txt").write_bytes(b"origen")
    (nueva / "r.txt").write_bytes(b"de la caja nueva")
    (nueva / ("r.txt" + mudanza.SUFIJO_COPIA)).write_bytes(b"otro distinto")
    copiados, faltan = mudanza._copiar_sin_pisar(str(vieja), str(nueva))
    assert (copiados, faltan) == (1, [])
    assert (nueva / "r.txt").read_bytes() == b"de la caja nueva"
    assert (nueva / ("r.txt" + mudanza.SUFIJO_COPIA)).read_bytes() == b"otro distinto"
    assert (nueva / ("r.txt" + mudanza.SUFIJO_COPIA + "-2")).read_bytes() == b"origen"


def test_carpeta_ilegible_cuenta_como_faltante(tmp_path, monkeypatch):
    """os.walk se salta en silencio lo que no puede leer: eso no puede darse por copiado."""
    vieja, nueva = tmp_path / "respaldos", tmp_path / "nueva"
    (vieja / "bloqueada").mkdir(parents=True)
    (vieja / "a.txt").write_bytes(b"a")
    real = os.walk

    def walk_con_error(top, onerror=None, **kw):
        for raiz, dirs, nombres in real(top, **kw):
            if os.path.basename(raiz) == "bloqueada":
                if onerror:
                    onerror(PermissionError(13, "Acceso denegado", raiz))
                continue
            yield raiz, dirs, nombres

    monkeypatch.setattr(mudanza.os, "walk", walk_con_error)
    copiados, faltan = mudanza._copiar_sin_pisar(str(vieja), str(nueva))
    assert copiados == 1
    assert any("bloqueada" in f for f in faltan)
