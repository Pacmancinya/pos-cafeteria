"""Cuadre de caja y la carta que consumen las pantallas del local."""


# ---------------------------------------------------------------- turnos
def test_cuadre_de_caja(cliente, carta):
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Ruperto", "monto_inicial": 20000})
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"})                                   # 3400 al cajón
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["latte"]["id"], "cantidad": 1}],
        "medio_pago": "debito"})                                     # NO va al cajón

    t = cliente.get("/api/v1/turnos/actual").json()["turno"]
    assert t["efectivo_esperado"] == 23400

    cierre = cliente.post("/api/v1/turnos/cerrar", json={"efectivo_contado": 23400, "nota": ""}).json()
    assert cierre["diferencia"] == 0


def test_el_descuadre_se_guarda_no_se_esconde(cliente, carta):
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Ana", "monto_inicial": 10000})
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["espresso"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo"})
    cierre = cliente.post("/api/v1/turnos/cerrar", json={"efectivo_contado": 11000, "nota": "faltó"}).json()
    assert cierre["efectivo_esperado"] == 11900
    assert cierre["diferencia"] == -900


def test_la_propina_en_efectivo_va_al_cajon(cliente, carta):
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Ana", "monto_inicial": 0})
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": carta["espresso"]["id"], "cantidad": 1}],
        "medio_pago": "efectivo", "propina": 500})
    t = cliente.get("/api/v1/turnos/actual").json()["turno"]
    assert t["efectivo_esperado"] == 2400


def test_no_se_abren_dos_turnos(cliente, carta):
    cliente.post("/api/v1/turnos/abrir", json={"cajero": "Ana", "monto_inicial": 0})
    assert cliente.post("/api/v1/turnos/abrir", json={"cajero": "Otro", "monto_inicial": 0}).status_code == 409


def test_cerrar_sin_turno_abierto(cliente):
    assert cliente.post("/api/v1/turnos/cerrar", json={"efectivo_contado": 0}).status_code == 409


# ---------------------------------------------------------------- carta
def test_formato_de_la_carta(cliente, carta):
    d = cliente.get("/api/v1/carta").json()
    assert set(d) >= {"avisos", "categorias"}
    cafe = next(c for c in d["categorias"] if c["nombre"] == "Café")
    assert cafe["destacado"]["nombre"] == "Mocha"
    assert cafe["destacado"]["etiqueta"] == "Hoy"
    # el destacado no se repite entre los productos normales
    assert "Mocha" not in [p["nombre"] for p in cafe["productos"]]
    p = cafe["productos"][0]
    assert set(p) == {"nombre", "descripcion", "precio", "antes", "etiqueta", "dibujo", "color"}


def test_la_carta_manda_cors(cliente, carta):
    """Sin esta cabecera el navegador de la pantalla rechaza la respuesta."""
    r = cliente.get("/api/v1/carta")
    assert r.headers.get("access-control-allow-origin") == "*"


def test_producto_apagado_no_sale_en_la_carta(cliente, carta):
    cliente.delete(f"/api/v1/productos/{carta['latte']['id']}")
    d = cliente.get("/api/v1/carta").json()
    cafe = next(c for c in d["categorias"] if c["nombre"] == "Café")
    assert "Latte" not in [p["nombre"] for p in cafe["productos"]]


def test_categoria_vacia_no_viaja(cliente, carta):
    """Una categoría sin productos rompe la pantalla: mejor no mandarla."""
    cliente.post("/api/v1/categorias", json={"nombre": "Vacía", "orden": 9})
    d = cliente.get("/api/v1/carta").json()
    assert "Vacía" not in [c["nombre"] for c in d["categorias"]]


def test_un_solo_destacado_por_categoria(cliente, carta):
    """Marcar otro destacado desmarca el anterior solo."""
    cliente.put(f"/api/v1/productos/{carta['latte']['id']}", json={
        **{k: v for k, v in carta["latte"].items() if k != "id"}, "destacado": True})
    d = cliente.get("/api/v1/carta").json()
    cafe = next(c for c in d["categorias"] if c["nombre"] == "Café")
    assert cafe["destacado"]["nombre"] == "Latte"
    cats = cliente.get("/api/v1/categorias").json()
    destacados = [p for c in cats for p in c["productos"] if p["destacado"]]
    assert len(destacados) == 1


def test_borrar_producto_es_de_verdad_y_la_venta_sigue_cuadrando(cliente, carta, caja):
    """Desde la 2.12 el borrado es REAL: la fila se va. Pero la venta vieja
    tiene que seguir cuadrando, porque VentaLinea guarda nombre y precio
    copiados."""
    lid = carta["latte"]["id"]
    cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": lid, "cantidad": 1}], "medio_pago": "efectivo"})
    assert cliente.delete(f"/api/v1/productos/{lid}").json().get("borrado") is True
    # La fila del producto YA NO EXISTE.
    assert cliente.get(f"/api/v1/productos/{lid}/receta").status_code == 404
    # Pero la venta sigue sumando: el informe del día no cambió.
    assert cliente.get("/api/v1/resumen").json()["total"] == 3400


# ---------------------------------------------------------------------------
# Editar y borrar categorías
# ---------------------------------------------------------------------------
"""Hasta la 2.11 una categoría solo se podía crear. El dueño no podía corregir
un nombre mal escrito ni sacar una categoría vacía que le quedó de una
importación. Editar cambia nombre y orden; borrar es de verdad, pero solo si la
categoría está vacía: un producto no puede quedar sin categoría."""


def test_editar_el_nombre_de_una_categoria(cliente, carta):
    cid = carta["cafe"]["id"]
    r = cliente.put(f"/api/v1/categorias/{cid}",
                    json={"nombre": "Cafés calientes", "orden": 2, "activa": True})
    assert r.status_code == 200, r.text
    assert r.json()["nombre"] == "Cafés calientes"
    assert r.json()["orden"] == 2


def test_no_se_deja_una_categoria_sin_nombre(cliente, carta):
    cid = carta["cafe"]["id"]
    assert cliente.put(f"/api/v1/categorias/{cid}",
                       json={"nombre": "   ", "orden": 0, "activa": True}).status_code == 422


def test_borrar_una_categoria_vacia(cliente):
    vacia = cliente.post("/api/v1/categorias", json={"nombre": "Provisoria", "orden": 9}).json()
    r = cliente.delete(f"/api/v1/categorias/{vacia['id']}")
    assert r.status_code == 200, r.text
    # Ya no aparece en la lista.
    ids = [c["id"] for c in cliente.get("/api/v1/categorias").json()]
    assert vacia["id"] not in ids


def test_no_se_borra_una_categoria_con_productos(cliente, carta):
    """La guarda: un producto no puede quedar sin categoría."""
    cid = carta["cafe"]["id"]
    r = cliente.delete(f"/api/v1/categorias/{cid}")
    assert r.status_code == 409
    assert "producto" in r.json()["detail"].lower()
    # Y de verdad NO se borró.
    ids = [c["id"] for c in cliente.get("/api/v1/categorias").json()]
    assert cid in ids


def test_una_categoria_con_solo_productos_apagados_tampoco_se_borra(cliente, carta):
    """Un producto APAGADO (no borrado) sigue apuntando a la categoría: borrarla
    lo dejaría huérfano igual. Se cuentan TODOS, no solo los que están a la venta.
    Apagar es la casilla «A la venta» (PUT activo=false), reversible; borrar de
    verdad es otra cosa."""
    cid = carta["cafe"]["id"]
    for p in ["espresso", "latte", "mocha"]:
        base = {k: v for k, v in carta[p].items() if k != "id"}
        cliente.put(f"/api/v1/productos/{carta[p]['id']}", json={**base, "activo": False})
    # La categoría no tiene productos ACTIVOS, pero sí productos apagados.
    r = cliente.delete(f"/api/v1/categorias/{cid}")
    assert r.status_code == 409, "una categoría con productos apagados no puede borrarse"


# ---------------------------------------------------------------------------
# Borrado REAL de productos (2.12)
# ---------------------------------------------------------------------------
"""Hasta la 2.11 borrar un producto solo lo apagaba (activo=False). Ahora la fila
se va de verdad. Estas pruebas miran la BASE directo a propósito: SQLite no tiene
las llaves foráneas activadas, así que un borrado que deje filas huérfanas pasa
sin error y sin romper ningún informe —hasta que el reciclaje de id se las pega
al siguiente producto—. Es el único bug que no se ve desde la API."""

from sqlmodel import Session, select
from apps.pos.db.session import engine
from apps.pos.db.models import Producto, Insumo, Receta, CodigoBarra, VentaLinea


def _tal_cual_con_codigo(cliente, cat_id, nombre, precio, codigo, stock):
    cuerpo = {"categoria_id": cat_id, "nombre": nombre, "precio": precio,
              "tal_cual": True, "stock_inicial": stock}
    if codigo:
        cuerpo["codigo"] = codigo
    r = cliente.post("/api/v1/productos", json=cuerpo)
    assert r.status_code == 200, r.text
    return r.json()


def test_borrar_no_deja_ni_una_huerfana(cliente, carta):
    """El id se recicla: una receta o un código que queden apuntando al id
    borrado se le pegan al próximo producto. No puede quedar ninguna."""
    p = _tal_cual_con_codigo(cliente, carta["cafe"]["id"], "Coca 1.5", 2500, "7801234567894", 5)
    pid = p["id"]
    cliente.delete(f"/api/v1/productos/{pid}")
    with Session(engine) as s:
        assert s.get(Producto, pid) is None
        assert s.exec(select(Receta).where(Receta.producto_id == pid)).first() is None
        assert s.exec(select(CodigoBarra).where(CodigoBarra.producto_id == pid)).first() is None


def test_borrar_conserva_el_insumo_y_su_libro(cliente, carta):
    """La mercadería sigue en la repisa: el insumo se queda, con su stock y sus
    movimientos. Solo se le suelta el vínculo con el producto."""
    p = _tal_cual_con_codigo(cliente, carta["cafe"]["id"], "Ron", 8000, "", 3)
    pid = p["id"]
    cliente.delete(f"/api/v1/productos/{pid}")
    with Session(engine) as s:
        insumo = s.exec(select(Insumo).where(Insumo.nombre == "Ron")).first()
        assert insumo is not None, "el insumo no se borra"
        assert insumo.producto_id is None, "pero deja de ser de ese producto"
        assert insumo.stock == 3, "y conserva su stock"


def test_la_venta_queda_sin_vinculo_pero_con_su_nombre(cliente, carta, caja):
    p = _tal_cual_con_codigo(cliente, carta["cafe"]["id"], "Fanta", 1500, "", 10)
    pid = p["id"]
    v = cliente.post("/api/v1/ventas", json={
        "lineas": [{"producto_id": pid, "cantidad": 2}], "medio_pago": "efectivo"}).json()
    cliente.delete(f"/api/v1/productos/{pid}")
    with Session(engine) as s:
        lineas = s.exec(select(VentaLinea).where(VentaLinea.venta_id == v["id"])).all()
        assert lineas, "la línea NO se borra"
        assert lineas[0].producto_id is None, "se le suelta el vínculo"
        assert lineas[0].nombre == "Fanta", "pero guarda el nombre copiado"


def test_borrar_y_recrear_no_duplica_el_insumo(cliente, carta):
    """El bug de la decisión 14, por la puerta del borrado: si al recrear el
    producto se creara OTRO insumo, quedarían dos con la mitad de la verdad."""
    cid = carta["cafe"]["id"]
    p1 = _tal_cual_con_codigo(cliente, cid, "Sprite", 1500, "", 7)
    cliente.delete(f"/api/v1/productos/{p1['id']}")
    # Se vuelve a crear el mismo producto.
    p2 = cliente.post("/api/v1/productos", json={
        "categoria_id": cid, "nombre": "Sprite", "precio": 1500, "tal_cual": True}).json()
    with Session(engine) as s:
        insumos = s.exec(select(Insumo).where(Insumo.nombre == "Sprite")).all()
        assert len(insumos) == 1, "se adopta el huérfano, no se crea otro"
        assert insumos[0].producto_id == p2["id"]
        assert insumos[0].stock == 7, "y recupera el stock que tenía"


def test_borrar_libera_el_codigo_de_barras(cliente, carta):
    """Borrado el producto, su código se puede volver a usar en otro."""
    cid = carta["cafe"]["id"]
    p1 = _tal_cual_con_codigo(cliente, cid, "Monster", 2000, "7803333333332", 4)
    cliente.delete(f"/api/v1/productos/{p1['id']}")
    # El mismo código, en un producto nuevo: no puede chocar.
    r = cliente.post("/api/v1/productos", json={
        "categoria_id": cid, "nombre": "Red Bull", "precio": 2200,
        "tal_cual": True, "codigo": "7803333333332"})
    assert r.status_code == 200, r.text
