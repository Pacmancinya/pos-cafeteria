"""Cuenta optativa, libro auditable y compatibilidad de la bodega unitaria."""
import pytest
from sqlmodel import Session, select

from apps.pos.db.models import Insumo, Movimiento, Producto, Receta
from apps.pos.db.session import engine


def test_interacciones_bodega_en_node():
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which('node')
    if not node:
        pytest.skip('No hay Node en este computador')
    r = subprocess.run([node, str(Path(__file__).with_name('bodega_ui.cjs'))],
                       capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr


def producto(cliente, carta, **extras):
    r = cliente.post('/api/v1/productos', json={
        'categoria_id': carta['dulce']['id'], 'nombre': 'Pastél unitario',
        'precio': 1500, **extras})
    assert r.status_code == 200, r.text
    return r.json()


def cambiar_cuenta(cliente, p, marcada):
    r = cliente.put(f"/api/v1/productos/{p['id']}", json={
        **p, 'llevar_cuenta': marcada})
    assert r.status_code == 200, r.text
    return r.json()


def filas(cliente):
    return cliente.get('/api/v1/bodega').json()['insumos']


def cantidad(cliente, i, n, motivo='conteo'):
    return cliente.put(f"/api/v1/bodega/{i['id']}/cantidad", json={
        'cantidad': n, 'stock_esperado': i['stock'], 'motivo': motivo})


def foto():
    with Session(engine) as s:
        return {m.__name__: [x.model_dump() for x in s.exec(select(m).order_by(m.id)).all()]
                for m in (Insumo, Receta, Movimiento)}


def test_alta_optativa_y_reinicio_no_crea_insumos(cliente, carta):
    from apps.pos.db.session import crear_tablas
    antes = foto()
    p = producto(cliente, carta)
    assert p['llevar_cuenta'] is False
    assert filas(cliente) == []
    crear_tablas()
    assert foto() == antes
    cambiar_cuenta(cliente, p, True)
    i, = filas(cliente)
    assert i['producto_id'] == p['id']
    assert (i['unidad'], i['compra_contenido'], i['stock']) == ('un', 1, 0)
    antes = foto()
    cambiar_cuenta(cliente, p, True)
    assert foto() == antes


def test_buscar_por_nombre_y_por_codigo(cliente, carta):
    p = producto(cliente, carta, llevar_cuenta=True, codigo='7801234567894')
    for q in ('pastel', 'UNITARIO', '7801234567894'):
        r = cliente.get('/api/v1/bodega', params={'q': q})
        assert r.status_code == 200
        assert [i['producto_id'] for i in r.json()['insumos']] == [p['id']]
    assert cliente.get('/api/v1/bodega', params={'q': 'Americano'}).json()['insumos'] == []


@pytest.mark.parametrize('motivo,n,tipo,texto', [
    ('llego', 12, 'compra', 'Llegó'), ('se perdio', 8, 'merma', 'Se perdió'),
    ('conteo', 7, 'ajuste', 'Conteo'), ('ajuste', 11, 'ajuste', 'Ajuste')])
def test_guardar_anota_delta_motivo_fecha_y_persona(cliente, carta, motivo, n, tipo, texto):
    u = cliente.post('/api/v1/usuarios', json={'nombre': 'Dueña', 'pin': '1234'}).json()
    assert cliente.post('/api/v1/sesion/entrar', json={
        'usuario_id': u['id'], 'pin': '1234'}).status_code == 200
    producto(cliente, carta, llevar_cuenta=True)
    assert cantidad(cliente, filas(cliente)[0], 10).status_code == 200
    i = filas(cliente)[0]
    assert cantidad(cliente, i, n, motivo).status_code == 200
    with Session(engine) as s:
        m = s.exec(select(Movimiento).order_by(Movimiento.id.desc())).first()
        assert (m.cantidad, m.saldo_despues, m.tipo, m.motivo) == (n - 10, n, tipo, texto)
        assert (m.usuario_id, m.hecho_por) == (u['id'], 'Dueña')
        assert m.creado_at is not None
    libro = cliente.get(f"/api/v1/inventario/insumos/{i['id']}/movimientos").json()
    assert libro['movimientos'][0]['quien'] == 'Dueña'


def test_venta_topea_y_desmarcar_conserva_datos(cliente, carta, caja):
    p = producto(cliente, carta, llevar_cuenta=True)
    pedido = {'lineas': [{'producto_id': p['id'], 'cantidad': 1}]}
    assert cliente.post('/api/v1/ventas', json=pedido).status_code == 409
    assert cantidad(cliente, filas(cliente)[0], 1, 'llego').status_code == 200
    assert cliente.post('/api/v1/ventas', json=pedido).status_code == 200
    assert filas(cliente)[0]['stock'] == 0
    assert cliente.post('/api/v1/ventas', json=pedido).status_code == 409
    antes = foto()
    cambiar_cuenta(cliente, p, False)
    assert filas(cliente) == []
    assert cliente.post('/api/v1/ventas', json=pedido).status_code == 200
    assert foto() == antes
    cambiar_cuenta(cliente, p, True)
    assert foto() == antes
    assert cliente.post('/api/v1/ventas', json=pedido).status_code == 409


def test_no_pisa_un_saldo_que_cambio(cliente, carta):
    producto(cliente, carta, llevar_cuenta=True)
    i = filas(cliente)[0]
    assert cantidad(cliente, i, 12, 'llego').status_code == 200
    antes = foto()
    assert cantidad(cliente, i, 8).status_code == 409
    assert foto() == antes


def test_cuenta_automatica_anterior_sin_conteo_queda_en_avanzado(cliente, carta, caja):
    p = producto(cliente, carta, tal_cual=True)
    antes = foto()
    assert filas(cliente) == []
    assert len(cliente.get('/api/v1/inventario').json()['insumos']) == 1
    assert foto() == antes
    # Conserva la receta anterior, sin imponer un tope nuevo al actualizar.
    assert cliente.post('/api/v1/ventas', json={
        'lineas': [{'producto_id': p['id'], 'cantidad': 1}]}).status_code == 200
    antes = foto()
    cambiar_cuenta(cliente, p, True)
    assert filas(cliente)[0]['stock'] == -1
    assert foto() == antes


@pytest.mark.parametrize('cuerpo', [
    {'cantidad': -1, 'motivo': 'ajuste'}, {'cantidad': 1.5, 'motivo': 'conteo'},
    {'cantidad': True, 'motivo': 'conteo'}, {'cantidad': 3, 'motivo': ''},
    {'cantidad': 3}, {'cantidad': 3, 'motivo': 'se perdio'}])
def test_cantidad_o_motivo_invalido_no_toca_libro(cliente, carta, cuerpo):
    producto(cliente, carta, llevar_cuenta=True)
    i = filas(cliente)[0]
    antes = foto()
    r = cliente.put(f"/api/v1/bodega/{i['id']}/cantidad", json={
        'stock_esperado': 0, **cuerpo})
    assert r.status_code == 422
    assert foto() == antes


def test_insumo_y_receta_anteriores_siguen_funcionando(cliente, carta, caja):
    p = producto(cliente, carta, tal_cual=True, stock_inicial=3, costo=500)
    with Session(engine) as s:
        assert s.get(Producto, p['id']).llevar_cuenta is None
    antes = foto()
    from apps.pos.db.session import crear_tablas
    crear_tablas()
    assert foto() == antes
    assert filas(cliente)[0]['stock'] == 3
    pedido = {'lineas': [{'producto_id': p['id'], 'cantidad': 2}]}
    assert cliente.post('/api/v1/ventas', json=pedido).status_code == 200
    assert filas(cliente)[0]['stock'] == 1
    assert cliente.post('/api/v1/ventas', json=pedido).status_code == 409


def test_cajero_no_puede_disfrazar_conteo_como_ajuste(cliente, carta):
    producto(cliente, carta, llevar_cuenta=True)
    i = filas(cliente)[0]
    u = cliente.post('/api/v1/usuarios', json={'nombre': 'Dueño', 'pin': '1234'}).json()
    cliente.post('/api/v1/sesion/entrar', json={'usuario_id': u['id'], 'pin': '1234'})
    c = cliente.post('/api/v1/usuarios', json={
        'nombre': 'Caja', 'pin': '4321', 'rol': 'cajero'}).json()
    cliente.post('/api/v1/sesion/entrar', json={'usuario_id': c['id'], 'pin': '4321'})
    antes = foto()
    for motivo in ('conteo', 'ajuste'):
        assert cantidad(cliente, i, 9, motivo).status_code == 403
    assert foto() == antes
