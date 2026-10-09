"""La ficha unificada conserva precios, permisos y el libro de bases instaladas."""
from pathlib import Path
import shutil
import subprocess

import pytest
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine, select
from apps.pos.db.models import Categoria, Insumo, Movimiento, Producto, Receta
from apps.pos.db.session import engine


def alta(cliente, carta, **extras):
    r = cliente.post('/api/v1/productos', json={'categoria_id': carta['dulce']['id'],
        'nombre': 'Producto de prueba', 'precio': 1500, **extras})
    assert r.status_code == 200, r.text
    return r.json()


def ficha(cliente, id):
    return next(p for p in cliente.get('/api/v1/inventario/productos').json()['productos'] if p['id'] == id)


def libro(id):
    with Session(engine) as s:
        i = s.exec(select(Insumo).where(Insumo.producto_id == id)).one()
        return i.model_dump(), [m.model_dump() for m in s.exec(
            select(Movimiento).where(Movimiento.insumo_id == i.id).order_by(Movimiento.id)).all()]


def test_tv_independiente_filtra_destacados_y_categorias(cliente, carta, caja):
    for p in (carta['espresso'], carta['latte'], carta['mocha'], carta['alfajor']):
        assert cliente.put(f"/api/v1/productos/{p['id']}", json={**p, 'en_tv': False}).status_code == 200
    assert cliente.get('/api/v1/carta').json()['categorias'] == []
    assert len(cliente.get('/api/v1/categorias').json()[0]['productos']) == 3
    assert cliente.post('/api/v1/ventas', json={'lineas': [
        {'producto_id': carta['espresso']['id'], 'cantidad': 1}]}).status_code == 200
    p = carta['mocha']
    cliente.put(f"/api/v1/productos/{p['id']}", json={**p, 'en_tv': True})
    c, = cliente.get('/api/v1/carta').json()['categorias']
    assert c['destacado']['nombre'] == p['nombre']
    assert all(x['nombre'] == p['nombre'] and x['en_tv'] for x in c['productos'])
    p = carta['espresso']
    cliente.put(f"/api/v1/productos/{p['id']}", json={k: v for k, v in p.items() if k != 'en_tv'})
    assert ficha(cliente, p['id'])['en_tv'] is False


def test_costo_sin_stock_se_guarda_y_pasa_al_insumo(cliente, carta):
    p = alta(cliente, carta, costo=800)
    assert ficha(cliente, p['id'])['costo'] == 800
    with Session(engine) as s:
        assert s.exec(select(Insumo).where(Insumo.producto_id == p['id'])).first() is None
    cliente.put(f"/api/v1/productos/{p['id']}", json={**p, 'llevar_cuenta': True})
    assert libro(p['id'])[0]['compra_costo'] == 800
    cliente.put(f"/api/v1/productos/{p['id']}", json={**p, 'costo': 0, 'minimo': 0})
    assert ficha(cliente, p['id'])['costo'] == 0


def test_costo_envase_y_entrada_en_unidades(cliente, carta):
    p = alta(cliente, carta, llevar_cuenta=True, costo=100)
    i, _ = libro(p['id'])
    with Session(engine) as s:
        insumo = s.get(Insumo, i['id'])
        insumo.compra_contenido, insumo.compra_costo = 12, 6000
        s.add(insumo); s.commit()
    assert ficha(cliente, p['id'])['costo'] == 500
    cliente.put(f"/api/v1/productos/{p['id']}", json={**p, 'costo': 700})
    i, movimientos = libro(p['id'])
    assert (i['compra_contenido'], i['compra_costo'], movimientos) == (12, 8400, [])
    assert cliente.post('/api/v1/inventario/compras', json={
        'insumo_id': i['id'], 'cantidad': 3, 'costo_unitario': 800}).status_code == 200
    assert libro(p['id'])[0]['stock'] == 3
    assert libro(p['id'])[0]['compra_costo'] == 9600


def test_carga_ajuste_interruptor_conserva_historia(cliente, carta, caja):
    p = alta(cliente, carta, llevar_cuenta=True, hay_ahora=5, stock_esperado=0, minimo=2)
    assert [(m['tipo'], m['cantidad']) for m in libro(p['id'])[1]] == [('carga', 5)]
    assert cliente.put(f"/api/v1/productos/{p['id']}", json={**p,
        'hay_ahora': 3, 'stock_esperado': 5, 'minimo': 0}).status_code == 200
    assert [(m['tipo'], m['cantidad']) for m in libro(p['id'])[1]] == [('carga', 5), ('ajuste', -2)]
    antes = libro(p['id'])
    cliente.put(f"/api/v1/productos/{p['id']}", json={**p, 'llevar_cuenta': False})
    assert not ficha(cliente, p['id'])['cuenta']
    assert cliente.post('/api/v1/ventas', json={'lineas': [
        {'producto_id': p['id'], 'cantidad': 20}]}).status_code == 200
    assert libro(p['id']) == antes
    cliente.put(f"/api/v1/productos/{p['id']}", json={**p, 'llevar_cuenta': True})
    assert libro(p['id']) == antes


def test_conflicto_de_stock_o_codigo_revierte_toda_ficha(cliente, carta):
    p = alta(cliente, carta, llevar_cuenta=True, hay_ahora=3, stock_esperado=0)
    antes = libro(p['id'])
    assert cliente.put(f"/api/v1/productos/{p['id']}", json={**p, 'hay_ahora': 9,
        'stock_esperado': 0, 'en_tv': False}).status_code == 409
    assert libro(p['id']) == antes and ficha(cliente, p['id'])['en_tv']
    cliente.post('/api/v1/productos', json={'categoria_id': p['categoria_id'],
        'nombre': 'Otra ficha', 'codigo': '7801234567894'})
    assert cliente.put(f"/api/v1/productos/{p['id']}", json={**p, 'hay_ahora': 9,
        'stock_esperado': 3, 'codigos': [{'codigo': '7801234567894'}]}).status_code == 409
    assert libro(p['id']) == antes


def test_codigos_atomicos_preservan_pack(cliente, carta):
    p = alta(cliente, carta, codigos=[{'codigo': '036000291452', 'cuantos': 6, 'nota': 'Pack'}])
    b, = ficha(cliente, p['id'])['codigos']
    assert b == {'codigo': '0036000291452', 'cuantos': 6, 'nota': 'Pack'}
    cliente.put(f"/api/v1/productos/{p['id']}", json={**p, 'codigos': [b], 'en_tv': False})
    assert ficha(cliente, p['id'])['codigos'] == [b]
    cliente.put(f"/api/v1/productos/{p['id']}", json={**p, 'codigos': []})
    assert ficha(cliente, p['id'])['codigos'] == []


def test_codigos_por_diferencias_conservan_los_de_otro_equipo(cliente, carta):
    p = alta(cliente, carta, codigos=[{'codigo': '7801234567894'}])
    # Otro equipo agrega un código mientras esta ficha seguía abierta con el original.
    assert cliente.put(f"/api/v1/productos/{p['id']}", json={**p, 'codigos': [
        {'codigo': '7801234567894'}, {'codigo': '7802345678905'}]}).status_code == 200
    assert cliente.put(f"/api/v1/productos/{p['id']}", json={**p, 'codigos': [],
        'codigos_quitar': []}).status_code == 200
    assert {b['codigo'] for b in ficha(cliente, p['id'])['codigos']} == {'7801234567894', '7802345678905'}
    assert cliente.put(f"/api/v1/productos/{p['id']}", json={**p, 'codigos': [{'codigo': '036000291452'}],
        'codigos_quitar': ['7801234567894']}).status_code == 200
    assert {b['codigo'] for b in ficha(cliente, p['id'])['codigos']} == {'7802345678905', '0036000291452'}


def test_inventario_oculta_stock_y_costo_sin_permiso_y_lista_ingredientes(cliente, carta, caja):
    p = alta(cliente, carta, llevar_cuenta=True, hay_ahora=5, stock_esperado=0, costo=300)
    i = cliente.post('/api/v1/inventario/insumos', json={'nombre': 'Leche antigua', 'unidad': 'ml',
        'compra_contenido': 1000, 'compra_costo': 1500, 'stock_inicial': 2000}).json()
    latte = carta['latte']
    cliente.put(f"/api/v1/productos/{latte['id']}/receta", json={'lineas': [{'insumo_id': i['id'], 'cantidad': 200}]})
    d = cliente.get('/api/v1/inventario/productos').json()
    assert [x['nombre'] for x in d['ingredientes']] == ['Leche antigua'] and d['ingredientes'][0]['stock'] == 2000
    assert next(x for x in d['productos'] if x['id'] == latte['id'])['costo'] == 300   # 200 ml de leche a $1.500 el litro
    u = cliente.post('/api/v1/usuarios', json={'nombre': 'Dueño prueba', 'pin': '1234'}).json()
    cliente.post('/api/v1/sesion/entrar', json={'usuario_id': u['id'], 'pin': '1234'})
    e = cliente.post('/api/v1/usuarios', json={'nombre': 'Editor prueba', 'pin': '4321',
        'rol': 'cajero', 'permisos': 'editar_carta'}).json()
    cliente.post('/api/v1/sesion/entrar', json={'usuario_id': e['id'], 'pin': '4321'})
    d = cliente.get('/api/v1/inventario/productos').json()
    fila = next(x for x in d['productos'] if x['id'] == p['id'])
    assert (fila['stock'], fila['costo'], fila['insumo_id'], fila['minimo']) == (0, None, None, 0)
    assert d['ingredientes'] == []


def test_receta_antigua_sigue_descontando(cliente, carta, caja):
    i = cliente.post('/api/v1/inventario/insumos', json={'nombre': 'Ingrediente antiguo',
        'unidad': 'ml', 'compra_contenido': 1000, 'compra_costo': 1000, 'stock_inicial': 1000}).json()
    p = carta['latte']
    cliente.put(f"/api/v1/productos/{p['id']}/receta", json={
        'lineas': [{'insumo_id': i['id'], 'cantidad': 200}]})
    assert ficha(cliente, p['id'])['receta_antigua']
    assert all(x['nombre'] != i['nombre'] for x in cliente.get('/api/v1/inventario/productos').json()['productos'])
    cuerpo = {k: v for k, v in p.items() if k != 'llevar_cuenta'}
    assert cliente.put(f"/api/v1/productos/{p['id']}", json={**cuerpo, 'costo': 900, 'en_tv': False}).status_code == 200
    assert cliente.put(f"/api/v1/productos/{p['id']}", json={**cuerpo, 'llevar_cuenta': True}).status_code == 409
    assert cliente.post('/api/v1/ventas', json={'lineas': [
        {'producto_id': p['id'], 'cantidad': 2}]}).status_code == 200
    with Session(engine) as s:
        assert s.get(Insumo, i['id']).stock == 600
        assert s.exec(select(Receta).where(Receta.producto_id == p['id'])).one().cantidad == 200


def test_permisos_catalogo_y_stock_separados(cliente, carta):
    p = alta(cliente, carta, llevar_cuenta=True, hay_ahora=5, stock_esperado=0)
    d = cliente.post('/api/v1/usuarios', json={'nombre': 'Dueño prueba', 'pin': '1234'}).json()
    cliente.post('/api/v1/sesion/entrar', json={'usuario_id': d['id'], 'pin': '1234'})
    u = cliente.post('/api/v1/usuarios', json={'nombre': 'Editor prueba', 'pin': '4321',
        'rol': 'cajero', 'permisos': 'editar_carta'}).json()
    cliente.post('/api/v1/sesion/entrar', json={'usuario_id': u['id'], 'pin': '4321'})
    assert cliente.get('/api/v1/inventario/productos').status_code == 200
    assert cliente.put(f"/api/v1/productos/{p['id']}", json={**p, 'en_tv': False}).status_code == 200
    for extras in ({'llevar_cuenta': False}, {'hay_ahora': 8, 'stock_esperado': 5}, {'minimo': 0}):
        assert cliente.put(f"/api/v1/productos/{p['id']}", json={**p, **extras}).status_code == 403
    assert cliente.post('/api/v1/inventario/mermas', json={'insumo_id': libro(p['id'])[0]['id'],
        'cantidad': 1, 'motivo': 'Roto'}).status_code == 403


def test_prender_la_cuenta_sin_contar_exige_poder_corregir_stock(cliente, carta, caja):
    # Un insumo nuevo nace «contado» y en cero: sin conteo la caja dejaría de vender el producto.
    p = alta(cliente, carta)
    d = cliente.post('/api/v1/usuarios', json={'nombre': 'Dueño prueba', 'pin': '1234'}).json()
    cliente.post('/api/v1/sesion/entrar', json={'usuario_id': d['id'], 'pin': '1234'})
    u = cliente.post('/api/v1/usuarios', json={'nombre': 'Jefe prueba', 'pin': '4321',
        'rol': 'cajero', 'permisos': 'editar_carta,inventario,vender'}).json()
    cliente.post('/api/v1/sesion/entrar', json={'usuario_id': u['id'], 'pin': '4321'})
    assert cliente.put(f"/api/v1/productos/{p['id']}", json={**p, 'llevar_cuenta': True}).status_code == 403
    with Session(engine) as s:
        assert s.exec(select(Insumo).where(Insumo.producto_id == p['id'])).first() is None
    assert cliente.post('/api/v1/ventas', json={'lineas': [
        {'producto_id': p['id'], 'cantidad': 1}]}).status_code == 200


def test_conteo_obsoleto_no_pisa_saldo(cliente, carta):
    p = alta(cliente, carta, llevar_cuenta=True)
    i, _ = libro(p['id'])
    assert cliente.post('/api/v1/inventario/conteo', json={'conteos': {str(i['id']): 9},
        'esperados': {str(i['id']): 8}}).status_code == 409
    assert libro(p['id'])[0]['stock'] == 0
    assert cliente.post('/api/v1/inventario/conteo', json={'conteos': {str(i['id']): -1}}).status_code == 422


def test_cantidad_sin_cuenta_no_se_ignora(cliente, carta):
    r = cliente.post('/api/v1/productos', json={'categoria_id': carta['dulce']['id'],
        'nombre': 'Sin inventario', 'hay_ahora': 5, 'stock_esperado': 0})
    assert r.status_code == 422
    with Session(engine) as s:
        assert not s.exec(select(Producto).where(Producto.nombre == 'Sin inventario')).first()


def test_migracion_base_vieja_preserva_datos(tmp_path, monkeypatch):
    from apps.pos.db import migraciones
    viejo = create_engine('sqlite:///' + str(tmp_path / 'vieja.db'))
    try:
        SQLModel.metadata.create_all(viejo)
        with Session(viejo) as s:
            s.add(Categoria(id=1, nombre='Categoría antigua'))
            s.add(Producto(id=1, categoria_id=1, nombre='Producto antiguo', precio=1800))
            s.add(Insumo(id=1, producto_id=1, nombre='Producto antiguo', unidad='un', stock=7, contado=True))
            s.add(Receta(id=1, producto_id=1, insumo_id=1, cantidad=1))
            s.add(Movimiento(id=1, insumo_id=1, tipo='carga', cantidad=7, saldo_despues=7))
            s.commit()
        with viejo.begin() as c:
            c.execute(text('ALTER TABLE producto DROP COLUMN en_tv'))
            c.execute(text('ALTER TABLE producto DROP COLUMN costo_referencia'))
            antes = {t: [dict(r) for r in c.execute(text('SELECT * FROM ' + t)).mappings()]
                     for t in ('producto', 'insumo', 'receta', 'movimiento')}
        monkeypatch.setattr(migraciones, 'engine', viejo)
        assert set(migraciones.poner_al_dia()) == {'producto.en_tv', 'producto.costo_referencia'}
        with viejo.connect() as c:
            for tabla, filas in antes.items():
                despues = list(c.execute(text('SELECT * FROM ' + tabla)).mappings())
                assert len(despues) == len(filas)
                assert [{k: d[k] for k in a} for a, d in zip(filas, despues)] == filas
            assert tuple(c.execute(text('SELECT en_tv, costo_referencia FROM producto')).one()) == (1, 0)
        assert migraciones.poner_al_dia() == []
    finally:
        viejo.dispose()


def test_inventario_en_node():
    node = shutil.which('node')
    if not node:
        pytest.skip('No hay Node')
    r = subprocess.run([node, str(Path(__file__).with_name('inventario_ui.cjs'))],
                       capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
