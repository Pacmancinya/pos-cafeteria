"""Inventario: insumos, recetas y el libro de movimientos.

Las dos reglas que estos tests defienden, porque son las que se olvidan:
  1. El stock NUNCA impide cobrar.
  2. Anular devuelve lo que la venta descontó DE VERDAD, no lo que la receta
     de hoy diría que consume.
"""
import pytest
from sqlmodel import select

from core.config import costo_de, mostrar_cantidad


# ------------------------------------------------------------------ unidades
@pytest.mark.parametrize("cantidad,unidad,texto", [
    (4200, "ml", "4,2 L"),
    (1000, "ml", "1 L"),
    (800, "ml", "800 ml"),
    (1700, "g", "1,7 kg"),
    (18, "g", "18 g"),
    (14, "un", "14"),
    (-200, "ml", "-200 ml"),
])
def test_las_cantidades_se_leen_en_litros_y_kilos(cantidad, unidad, texto):
    """Se guarda en mililitros pero el dueño piensa en litros."""
    assert mostrar_cantidad(cantidad, unidad) == texto


def test_el_costo_divide_al_final():
    """$1.200 la caja de 1 L son $1,2 el ml. Si se guardara el costo por
    mililitro redondeado a $1, el inventario valdría un 17% menos."""
    assert costo_de(200, 1200, 1000) == 240
    assert costo_de(1000, 1200, 1000) == 1200
    assert costo_de(18, 12000, 1000) == 216
    assert costo_de(5, 100, 0) == 0          # sin contenido no revienta


# ------------------------------------------------------------------ fixtures
@pytest.fixture()
def bodega(cliente, carta):
    """Leche y café cargados, y el latte con su receta."""
    leche = cliente.post("/api/v1/inventario/insumos", json={
        "nombre": "Leche entera", "unidad": "ml", "minimo": 2000,
        "formato": "Caja 1 L", "compra_contenido": 1000, "compra_costo": 1200,
        "stock_inicial": 4000}).json()
    cafe = cliente.post("/api/v1/inventario/insumos", json={
        "nombre": "Café en grano", "unidad": "g", "minimo": 500,
        "formato": "Bolsa 1 kg", "compra_contenido": 1000, "compra_costo": 12000,
        "stock_inicial": 1000}).json()
    cliente.put(f"/api/v1/productos/{carta['latte']['id']}/receta", json={"lineas": [
        {"insumo_id": leche["id"], "cantidad": 200},
        {"insumo_id": cafe["id"], "cantidad": 18}]})
    return {"leche": leche, "cafe": cafe}


def _stock(cliente, nombre):
    datos = cliente.get("/api/v1/inventario").json()
    return next(i for i in datos["insumos"] if i["nombre"] == nombre)["stock"]


# ------------------------------------------------------------------ el libro
def test_la_carga_inicial_queda_en_el_libro(cliente, bodega):
    mv = cliente.get(f"/api/v1/inventario/insumos/{bodega['leche']['id']}/movimientos").json()
    assert len(mv["movimientos"]) == 1
    assert mv["movimientos"][0]["tipo"] == "carga"
    assert mv["movimientos"][0]["saldo_despues"] == 4000


def test_vender_descuenta_segun_la_receta(cliente, bodega, carta, caja):
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 3}]})
    assert _stock(cliente, "Leche entera") == 4000 - 600
    assert _stock(cliente, "Café en grano") == 1000 - 54


def test_un_producto_sin_receta_se_vende_y_no_mueve_nada(cliente, bodega, carta, caja):
    """Es el estado normal el primer día. No es un error y no avisa nada."""
    antes = _stock(cliente, "Leche entera")
    r = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["alfajor"]["id"], "cantidad": 2}]})
    assert r.status_code == 200
    assert _stock(cliente, "Leche entera") == antes


def test_el_stock_en_cero_no_impide_cobrar(cliente, bodega, carta, caja):
    """Hay cola en el mostrador y el cliente ya pagó con tarjeta. Si el POS se
    negara, el cajero solo podría mentirle al cliente o anotar la venta en un
    papel: las dos cosas son peores que un número de stock equivocado."""
    r = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 40}]})
    assert r.status_code == 200
    assert _stock(cliente, "Leche entera") == 4000 - 8000     # queda negativo
    # ...pero avisa.
    assert any(a["bajo_cero"] for a in r.json()["inventario"])


def test_el_saldo_negativo_es_informacion(cliente, bodega, carta, caja):
    """−4 L dice 'vendiste más lattes que la leche que tus papeles dicen que
    tenías', o sea hay una compra sin registrar. Bloquear destruiría esa señal."""
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 25}]})
    alertas = cliente.get("/api/v1/inventario/alertas").json()
    assert any(f["bajo_cero"] for f in alertas["por_comprar"])


# ------------------------------------------------------------------ anular
def test_anular_devuelve_lo_que_la_venta_descontó(cliente, bodega, carta, caja):
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 2}]}).json()
    assert _stock(cliente, "Leche entera") == 3600
    cliente.post(f"/api/v1/ventas/{v['id']}/anular", json={"motivo": "se equivocó"})
    assert _stock(cliente, "Leche entera") == 4000


def test_anular_lee_el_libro_no_la_receta_de_hoy(cliente, bodega, carta, caja):
    """Si entremedio alguien cambia el latte de 200 a 100 ml, recalcular
    devolvería 100 y se perderían 100 ml para siempre sin que nadie lo note."""
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}]}).json()
    cliente.put(f"/api/v1/productos/{carta['latte']['id']}/receta", json={"lineas": [
        {"insumo_id": bodega["leche"]["id"], "cantidad": 100}]})
    cliente.post(f"/api/v1/ventas/{v['id']}/anular", json={"motivo": "x"})
    assert _stock(cliente, "Leche entera") == 4000       # los 200 que salieron


def test_anular_dos_veces_no_devuelve_dos_veces(cliente, bodega, carta, caja):
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}]}).json()
    cliente.post(f"/api/v1/ventas/{v['id']}/anular", json={"motivo": "x"})
    cliente.post(f"/api/v1/ventas/{v['id']}/anular", json={"motivo": "x"})   # 409
    assert _stock(cliente, "Leche entera") == 4000


def test_una_venta_anterior_a_la_receta_no_devuelve_nada(cliente, carta, caja):
    """Sin caso especial: no escribió movimientos, así que no hay qué devolver."""
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}]}).json()
    assert cliente.post(f"/api/v1/ventas/{v['id']}/anular",
                        json={"motivo": "x"}).status_code == 200


# ------------------------------------------------------- compras y mermas
def test_una_compra_entra_en_envases(cliente, bodega):
    r = cliente.post("/api/v1/inventario/compras", json={
        "insumo_id": bodega["leche"]["id"], "envases": 6}).json()
    assert r["stock"] == 4000 + 6000
    assert r["muestra"] == "10 L"


def test_el_ultimo_costo_pasa_a_ser_el_costo(cliente, bodega):
    r = cliente.post("/api/v1/inventario/compras", json={
        "insumo_id": bodega["leche"]["id"], "envases": 1, "compra_costo": 1500}).json()
    assert r["compra_costo"] == 1500


def test_una_merma_sin_motivo_no_se_guarda(cliente, bodega):
    """Una merma sin motivo no se distingue de un faltante."""
    assert cliente.post("/api/v1/inventario/mermas", json={
        "insumo_id": bodega["leche"]["id"], "cantidad": 500}).status_code == 422
    r = cliente.post("/api/v1/inventario/mermas", json={
        "insumo_id": bodega["leche"]["id"], "cantidad": 500,
        "motivo": "se cayó la caja"})
    assert r.status_code == 200
    assert r.json()["costo"] == 600


# ------------------------------------------------------------------ conteo
def test_el_conteo_solo_anota_lo_que_no_cuadra(cliente, bodega):
    r = cliente.post("/api/v1/inventario/conteo", json={"conteos": {
        str(bodega["leche"]["id"]): 3800,      # faltan 200
        str(bodega["cafe"]["id"]): 1000,       # cuadra
    }}).json()
    assert r["ajustados"] == 1 and r["sin_cambios"] == 1
    assert r["diferencias"][0]["diferencia"] == -200
    assert _stock(cliente, "Leche entera") == 3800


def test_el_conteo_le_pone_precio_al_descuadre(cliente, bodega):
    r = cliente.post("/api/v1/inventario/conteo", json={"conteos": {
        str(bodega["leche"]["id"]): 3000}}).json()      # faltan 1000 ml = $1.200
    assert r["costo_del_descuadre"] == -1200


def test_el_conteo_es_cosa_del_dueno(cliente, bodega, carta):
    # El primer usuario SIEMPRE es dueño, así que primero va él.
    d = cliente.post("/api/v1/usuarios", json={"nombre": "Ruperto", "pin": "1234"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": d["id"], "pin": "1234"})
    javi = cliente.post("/api/v1/usuarios",
                        json={"nombre": "Javi", "pin": "4321", "rol": "cajero"}).json()
    cliente.post("/api/v1/sesion/entrar", json={"usuario_id": javi["id"], "pin": "4321"})
    # El cajero mira la bodega y anota mermas, pero no ajusta saldos.
    assert cliente.get("/api/v1/inventario").status_code == 200
    assert cliente.post("/api/v1/inventario/conteo",
                        json={"conteos": {}}).status_code == 403


# ------------------------------------------------------------------ recetas
def test_el_saldo_es_la_suma_del_libro(cliente, bodega, carta):
    """`Insumo.stock` es una copia rápida. Si alguna vez se despega del libro,
    el que manda es el libro."""
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 2}]})
    cliente.post("/api/v1/inventario/compras", json={
        "insumo_id": bodega["leche"]["id"], "envases": 2})
    r = cliente.post("/api/v1/inventario/recalcular").json()
    assert r["corregidos"] == []          # nada que corregir: ya cuadraba


def test_la_receta_dice_el_costo_y_para_cuantos_alcanza(cliente, bodega, carta):
    r = cliente.get(f"/api/v1/productos/{carta['latte']['id']}/receta").json()
    assert r["costo_total"] == 240 + 216            # leche + café
    assert r["margen"] == 3400 - 456
    # 4000 ml / 200 = 20 lattes · 1000 g / 18 = 55: manda el que se acaba antes
    assert r["alcanza_para"] == 20


def test_se_vende_tal_cual_arma_todo_de_un_toque(cliente, carta, caja):
    """El atajo del día 1: el alfajor pasa a tener stock sin que nadie tenga
    que entender la palabra insumo."""
    r = cliente.post(f"/api/v1/productos/{carta['alfajor']['id']}/receta/tal-cual",
                     json={"stock_inicial": 12, "minimo": 4, "compra_costo": 700}).json()
    assert r["lineas"][0]["nombre"] == "Alfajor"
    assert r["lineas"][0]["cantidad"] == 1
    assert _stock(cliente, "Alfajor") == 12

    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["alfajor"]["id"], "cantidad": 3}]})
    assert _stock(cliente, "Alfajor") == 9


def test_sacar_un_insumo_no_borra_su_historia(cliente, bodega):
    cliente.delete(f"/api/v1/inventario/insumos/{bodega['leche']['id']}")
    assert "Leche entera" not in [i["nombre"] for i in
                                  cliente.get("/api/v1/inventario").json()["insumos"]]
    mv = cliente.get(f"/api/v1/inventario/insumos/{bodega['leche']['id']}/movimientos").json()
    assert len(mv["movimientos"]) == 1


# ------------------------------------- un solo lugar para agregar un producto
def test_crear_un_producto_tal_cual_deja_todo_hecho(cliente, carta):
    """La queja del dueño, textual: «es bien incómodo tener que agregar
    productos en carta y en bodega». Un formulario tiene que dejar la ficha, el
    insumo, la receta y el saldo — todo, o nada."""
    p = cliente.post("/api/v1/productos", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "Alfajor grande",
        "precio": 1500, "tal_cual": True, "costo": 700,
        "stock_inicial": 20, "minimo": 5}).json()

    inv = cliente.get("/api/v1/inventario").json()
    suyo = [i for i in inv["insumos"] if i["producto_id"] == p["id"]]
    assert len(suyo) == 1, "tiene que quedar UN insumo, amarrado por id"
    assert suyo[0]["nombre"] == "Alfajor grande"
    assert suyo[0]["stock"] == 20
    assert suyo[0]["compra_costo"] == 700
    assert suyo[0]["minimo"] == 5

    r = cliente.get(f"/api/v1/productos/{p['id']}/receta").json()
    assert len(r["lineas"]) == 1
    assert r["costo_total"] == 700


def test_vender_lo_creado_asi_descuenta_el_stock(cliente, carta, caja):
    """Que quede amarrado no basta: tiene que descontar de verdad."""
    p = cliente.post("/api/v1/productos", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "Botella de agua",
        "precio": 1000, "tal_cual": True, "costo": 400,
        "stock_inicial": 10}).json()
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": p["id"], "cantidad": 3}]})

    inv = cliente.get("/api/v1/inventario").json()
    suyo = [i for i in inv["insumos"] if i["producto_id"] == p["id"]][0]
    assert suyo["stock"] == 7


def test_renombrar_el_producto_renombra_su_insumo(cliente, carta):
    """En la base real quedó un insumo llamado «Producto nuevo» apuntando a un
    producto llamado «redbul 550ml». El dueño abre la bodega, no reconoce nada,
    y termina creando otro."""
    p = cliente.post("/api/v1/productos", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "Producto nuevo",
        "precio": 1000, "tal_cual": True}).json()
    cliente.put(f"/api/v1/productos/{p['id']}", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "Red Bull 550 ml",
        "precio": 1000})

    inv = cliente.get("/api/v1/inventario").json()
    suyo = [i for i in inv["insumos"] if i["producto_id"] == p["id"]][0]
    assert suyo["nombre"] == "Red Bull 550 ml"


# --------------------------------------------- el bug del nombre repetido
def test_no_se_pueden_crear_dos_insumos_con_el_mismo_nombre(cliente):
    """Se creaban dos en silencio y quedaban dos saldos, cada uno con la mitad
    de la verdad."""
    assert cliente.post("/api/v1/inventario/insumos", json={
        "nombre": "Leche entera", "unidad": "ml"}).status_code == 200
    r = cliente.post("/api/v1/inventario/insumos", json={
        "nombre": "Leche entera", "unidad": "ml"})
    assert r.status_code == 409
    assert "Leche entera" in r.json()["detail"]


def test_las_tildes_y_los_espacios_no_hacen_un_insumo_distinto(cliente):
    """«Coca-Cola 1.5 L» y «coca cola 1.5 l» son la misma botella para cualquier
    persona. El `==` crudo de antes decía que no."""
    cliente.post("/api/v1/inventario/insumos", json={"nombre": "Café en grano", "unidad": "g"})
    r = cliente.post("/api/v1/inventario/insumos", json={"nombre": "CAFE EN GRANO", "unidad": "g"})
    assert r.status_code == 409


def test_tampoco_se_puede_renombrar_encima_de_otro(cliente):
    cliente.post("/api/v1/inventario/insumos", json={"nombre": "Azúcar", "unidad": "g"})
    otro = cliente.post("/api/v1/inventario/insumos",
                        json={"nombre": "Harina", "unidad": "g"}).json()
    r = cliente.put(f"/api/v1/inventario/insumos/{otro['id']}",
                    json={"nombre": "azucar", "unidad": "g"})
    assert r.status_code == 409


def test_un_insumo_sacado_de_la_bodega_igual_protege_su_nombre(cliente):
    """Su libro de movimientos sigue ahí. Dejar que otro le tome el nombre deja
    dos historias mezcladas para siempre."""
    i = cliente.post("/api/v1/inventario/insumos",
                     json={"nombre": "Sirope", "unidad": "ml"}).json()
    cliente.delete(f"/api/v1/inventario/insumos/{i['id']}")
    r = cliente.post("/api/v1/inventario/insumos", json={"nombre": "Sirope", "unidad": "ml"})
    assert r.status_code == 409
    assert "sacado" in r.json()["detail"]


def test_la_migracion_amarra_y_renombra_lo_que_venia_de_antes(cliente, carta):
    """La base real llegó a la 2.3 con un insumo llamado «Producto nuevo»
    amarrado por receta a un producto llamado «redbul 550ml». La migración tiene
    que traducir esa relación a un id y de paso arreglarle el nombre."""
    from sqlmodel import Session, select

    from apps.pos.db.migraciones import _amarrar_insumos_a_su_producto
    from apps.pos.db.models import Insumo, Receta
    from apps.pos.db.session import engine

    p = cliente.post("/api/v1/productos", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "Red Bull 550 ml",
        "precio": 2500}).json()
    i = cliente.post("/api/v1/inventario/insumos", json={
        "nombre": "Producto nuevo", "unidad": "un"}).json()

    # Como quedaban antes: amarrados solo por la receta, sin producto_id.
    with Session(engine) as s:
        s.add(Receta(producto_id=p["id"], insumo_id=i["id"], cantidad=1))
        s.commit()

    hechos = _amarrar_insumos_a_su_producto()
    assert hechos, "la migración tenía que hacer algo"

    with Session(engine) as s:
        quedo = s.exec(select(Insumo).where(Insumo.id == i["id"])).first()
        assert quedo.producto_id == p["id"]
        assert quedo.nombre == "Red Bull 550 ml"

    # Y es idempotente: la segunda vez no encuentra nada que hacer.
    assert _amarrar_insumos_a_su_producto() == []


def test_la_migracion_no_toca_una_receta_de_verdad(cliente, carta):
    """Un capuchino NO «es» la leche. Solo se amarra el caso de una línea."""
    from sqlmodel import Session, select

    from apps.pos.db.migraciones import _amarrar_insumos_a_su_producto
    from apps.pos.db.models import Insumo, Receta
    from apps.pos.db.session import engine

    leche = cliente.post("/api/v1/inventario/insumos",
                         json={"nombre": "Leche", "unidad": "ml"}).json()
    cafe = cliente.post("/api/v1/inventario/insumos",
                        json={"nombre": "Café molido", "unidad": "g"}).json()
    with Session(engine) as s:
        s.add(Receta(producto_id=carta["latte"]["id"], insumo_id=leche["id"], cantidad=200))
        s.add(Receta(producto_id=carta["latte"]["id"], insumo_id=cafe["id"], cantidad=18))
        s.commit()

    _amarrar_insumos_a_su_producto()
    with Session(engine) as s:
        assert s.exec(select(Insumo).where(Insumo.id == leche["id"])).first().producto_id is None


# ------------------------------- productos sin cuenta: el agujero del video
def test_no_se_pueden_crear_dos_productos_con_el_mismo_nombre(cliente, carta):
    """En la carta del local quedaron NUEVE llamados «Producto nuevo». Dos con
    el mismo nombre no es estético: el cajero no sabe cuál tocar, «lo más
    vendido» los cuenta por separado, y el stock de uno no dice nada del otro."""
    r = cliente.post("/api/v1/productos", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "Latte", "precio": 3400})
    assert r.status_code == 409
    assert "Latte" in r.json()["detail"]


def test_las_tildes_no_hacen_un_producto_distinto(cliente, carta):
    r = cliente.post("/api/v1/productos", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "LATTE", "precio": 1})
    assert r.status_code == 409


def test_renombrar_encima_de_otro_tampoco(cliente, carta):
    r = cliente.put(f"/api/v1/productos/{carta['espresso']['id']}", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "Latte", "precio": 1900})
    assert r.status_code == 409


def test_un_producto_sacado_de_la_carta_libera_su_nombre(cliente, carta):
    """Ya no se puede tocar ni vender: su nombre puede volver a usarse."""
    cliente.delete(f"/api/v1/productos/{carta['latte']['id']}")
    assert cliente.post("/api/v1/productos", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "Latte",
        "precio": 3600}).status_code == 200


def test_llevar_la_cuenta_de_todo_le_da_inventario_a_los_que_no_tienen(cliente, carta):
    """El agujero que se vio en video: un producto sin inventario NO TIENE TOPE,
    y se vendieron 27 unidades de algo que no existía. Arreglarlos de a uno son
    treinta clics."""
    antes = cliente.get("/api/v1/inventario").json()
    assert antes["productos_con_receta"] == 0

    r = cliente.post("/api/v1/inventario/llevar-la-cuenta-de-todo").json()
    assert r["cuantos"] == 4                      # los cuatro de la carta de prueba

    inv = cliente.get("/api/v1/inventario").json()
    assert inv["productos_con_receta"] == 4
    # Y ahora la carta dice cuántos quedan: cero, que es la verdad.
    cats = cliente.get("/api/v1/categorias").json()
    for c in cats:
        for p in c["productos"]:
            assert p["stock"] == 0


def test_no_le_toca_el_inventario_a_los_que_ya_lo_llevaban(cliente, carta):
    p = cliente.post("/api/v1/productos", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "Botella",
        "precio": 1000, "tal_cual": True, "stock_inicial": 12}).json()

    cliente.post("/api/v1/inventario/llevar-la-cuenta-de-todo")
    inv = cliente.get("/api/v1/inventario").json()
    suyos = [i for i in inv["insumos"] if i["producto_id"] == p["id"]]
    assert len(suyos) == 1, "no se le crea un segundo insumo"
    assert suyos[0]["stock"] == 12, "y no se le pisa el saldo"


def test_no_le_toca_el_inventario_a_lo_que_tiene_receta_de_verdad(cliente, carta):
    """Un capuchino no ES un insumo: se hace con leche y café."""
    from sqlmodel import Session

    from apps.pos.db.models import Receta
    from apps.pos.db.session import engine
    leche = cliente.post("/api/v1/inventario/insumos",
                         json={"nombre": "Leche", "unidad": "ml"}).json()
    with Session(engine) as s:
        s.add(Receta(producto_id=carta["latte"]["id"], insumo_id=leche["id"], cantidad=200))
        s.commit()

    cliente.post("/api/v1/inventario/llevar-la-cuenta-de-todo")
    inv = cliente.get("/api/v1/inventario").json()
    suyos = [i for i in inv["insumos"] if i["producto_id"] == carta["latte"]["id"]]
    assert not suyos, "el latte no se convierte en su propio insumo"


def test_los_duplicados_que_ya_estaban_se_pueden_seguir_editando(cliente, carta):
    """La regla nueva no puede congelar la carta que ya existe.

    En el local hay NUEVE «Producto nuevo» de antes de esta versión. Si validar
    el nombre repetido pasara también cuando no lo cambian, guardarles el precio
    daría 409 y quedarían inarreglables — justo lo contrario de lo que se busca.
    """
    from sqlmodel import Session

    from apps.pos.db.models import Producto
    from apps.pos.db.session import engine
    with Session(engine) as s:                      # dos gemelos, como en el local
        s.add(Producto(categoria_id=carta["cafe"]["id"], nombre="Producto nuevo",
                       precio=1000, activo=True))
        s.add(Producto(categoria_id=carta["cafe"]["id"], nombre="Producto nuevo",
                       precio=1000, activo=True))
        s.commit()
        gemelos = [p.id for p in s.exec(
            select(Producto).where(Producto.nombre == "Producto nuevo")).all()]
    assert len(gemelos) == 2

    # Cambiarle el precio sin tocar el nombre: tiene que dejar.
    r = cliente.put(f"/api/v1/productos/{gemelos[0]}", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "Producto nuevo", "precio": 2500})
    assert r.status_code == 200, r.text
    assert r.json()["precio"] == 2500

    # Y renombrarlo a algo libre —que es lo que hay que hacer— también.
    assert cliente.put(f"/api/v1/productos/{gemelos[1]}", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "Red Bull 250",
        "precio": 2500}).status_code == 200

    # Lo que sigue prohibido es CREAR una colisión nueva.
    assert cliente.put(f"/api/v1/productos/{gemelos[0]}", json={
        "categoria_id": carta["cafe"]["id"], "nombre": "Red Bull 250",
        "precio": 2500}).status_code == 409
