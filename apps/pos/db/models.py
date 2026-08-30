"""Modelo de datos del punto de venta.

Fuente de verdad: este archivo. El documento que lo explica es docs/CONTRATO.md
y hay que actualizarlo en el mismo commit cuando esto cambie.

Todos los montos son ENTEROS en pesos chilenos. Ver CONTRATO, decisión 1.
"""
# OJO: este archivo NO lleva "from __future__ import annotations".
# Con esa importación las anotaciones quedan como texto y SQLModel ya no puede
# resolver Relationship(List["Producto"]) — revienta al abrir la base.
from datetime import datetime
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel

from core.config import ahora


class Categoria(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    nombre: str
    orden: int = 0
    activa: bool = True

    productos: List["Producto"] = Relationship(back_populates="categoria")


class Producto(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    categoria_id: int = Field(foreign_key="categoria.id", index=True)
    nombre: str
    descripcion: str = ""
    precio: int = 0                       # bruto, con IVA incluido
    activo: bool = True
    orden: int = 0

    # Estos campos no los usa la caja para vender: viajan a las pantallas del local.
    destacado: bool = False               # va al recuadro grande (1 por categoría)
    badge: str = ""                       # etiqueta del recuadro grande
    antes: Optional[int] = None           # precio tachado de oferta
    etiqueta: str = ""                    # globito: "Nuevo", "Sin lactosa"…
    dibujo: str = "mug"                   # mug | taza | vaso | frappe | croissant | torta | brownie | alfajor
    color: str = ""

    categoria: Optional[Categoria] = Relationship(back_populates="productos")


class Usuario(SQLModel, table=True):
    """Quién trabaja en la caja.

    Existe para poder contestar tres preguntas que antes no se podían: quién
    abrió, quién cerró y quién estuvo. El PIN se guarda hasheado y NUNCA sale
    por la API.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    nombre: str = Field(index=True)        # como se le dice en el local: "Javi"
    rol: str = "cajero"                    # dueno | cajero (ver core.config.PERMISOS)
    pin_hash: str = ""                     # pbkdf2_sha256$iteraciones$sal$hash
    activo: bool = True                    # borrado lógico: las ventas apuntan acá
    color: str = ""                        # su tarjeta en la pantalla de candado
    orden: int = 0
    creado_at: datetime = Field(default_factory=ahora)
    ultimo_ingreso_at: Optional[datetime] = None


class Presencia(SQLModel, table=True):
    """Quién estuvo en la caja, desde cuándo hasta cuándo.

    Con solo el usuario de cada venta, alguien que atendió dos horas sin vender
    nada sería invisible. El requisito era saber quién ESTUVO en el turno.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    turno_id: Optional[int] = Field(default=None, foreign_key="turno.id", index=True)
    entro_at: datetime = Field(default_factory=ahora, index=True)
    salio_at: Optional[datetime] = None     # nulo = está adentro ahora mismo
    salida_por: str = ""                    # cambio | bloqueo | salir | cierre


class Turno(SQLModel, table=True):
    """Una jornada de caja. El cierre compara lo contado con lo esperado."""
    id: Optional[int] = Field(default=None, primary_key=True)
    # El nombre se mantiene COPIADO además del id: es lo único que tienen los
    # turnos anteriores al login, y congela cómo se llamaba la persona ese día.
    cajero: str = ""
    abierto_por_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    cerrado_por_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    abierto_at: datetime = Field(default_factory=ahora)
    cerrado_at: Optional[datetime] = None
    monto_inicial: int = 0
    efectivo_contado: Optional[int] = None
    diferencia: Optional[int] = None      # contado - esperado; se guarda aunque descuadre
    nota: str = ""

    # El detalle de cuántos billetes y monedas de cada uno se contaron, como
    # JSON: {"20000": 2, "1000": 7}. Guardarlo permite mirar después DÓNDE
    # estuvo el error, en vez de solo saber que faltaban $2.500.
    conteo_apertura: str = ""
    conteo_cierre: str = ""

    # Al cerrar, parte del efectivo se retira y parte queda de fondo para mañana.
    retiro: int = 0
    fondo_siguiente: int = 0

    # Lo que dice la máquina del banco y la app del banco, escrito al cerrar:
    # {"debito": 123400, "transferencia": 20000}. El efectivo se CUENTA; esto
    # se COPIA de otro comprobante, y por eso se guarda aparte: la diferencia
    # entre lo que dice el POS y lo que dice Transbank es su propia pregunta.
    conteo_medios: str = ""


class Venta(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    numero: int = Field(index=True)       # correlativo global, parte en 1
    turno_id: Optional[int] = Field(default=None, foreign_key="turno.id", index=True)
    creada_at: datetime = Field(default_factory=ahora, index=True)
    estado: str = "pagada"                # pagada | anulada
    total: int = 0                        # suma de las líneas, a precio de lista
    descuento: int = 0                    # rebaja aplicada; lo cobrado es total - descuento
    propina: int = 0
    medio_pago: str = "efectivo"
    nota: str = ""
    anulada_at: Optional[datetime] = None
    anulada_motivo: str = ""

    # Quién cobró y quién anuló. Nulo en las ventas anteriores al login: a esas
    # no se les inventa un autor.
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id", index=True)
    anulada_por_id: Optional[int] = Field(default=None, foreign_key="usuario.id")

    lineas: List["VentaLinea"] = Relationship(
        back_populates="venta",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class VentaLinea(SQLModel, table=True):
    """El nombre y el precio van COPIADOS: si mañana sube el café, la venta de
    ayer no cambia. Un POS que recalcula el pasado miente en el cuadre."""
    id: Optional[int] = Field(default=None, primary_key=True)
    venta_id: int = Field(foreign_key="venta.id", index=True)
    producto_id: Optional[int] = Field(default=None, foreign_key="producto.id")
    nombre: str
    precio_unitario: int
    cantidad: int = 1
    subtotal: int = 0

    venta: Optional[Venta] = Relationship(back_populates="lineas")


# ===========================================================================
# Inventario
# ===========================================================================
# Una cafetería tiene dos casos que parecen distintos y no lo son: el alfajor
# que se vende tal cual, y el latte que consume leche y café de un tarro
# compartido. Se resuelven con el MISMO modelo: el alfajor también es un Insumo
# (unidad "un") y su producto tiene una receta de una línea. Un solo camino de
# código, un solo saldo. Con dos mecanismos, el día que exista el combo
# "café + alfajor" el alfajor saldría de dos lados y los números dejarían de
# cuadrar.


class Insumo(SQLModel, table=True):
    """Lo que de verdad se guarda en la bodega."""
    id: Optional[int] = Field(default=None, primary_key=True)
    nombre: str = Field(index=True)
    unidad: str = "un"                    # g | ml | un — la unidad BASE
    # Saldo en unidad base. Es una COPIA rápida de la suma del libro, no la
    # verdad: la verdad es Movimiento. Puede quedar NEGATIVO y eso no es un
    # error — significa que hay una compra o una merma sin registrar.
    stock: int = 0
    minimo: int = 0                       # bajo esto aparece en "Por comprar"
    activo: bool = True                   # borrado lógico: el libro lo referencia
    orden: int = 0

    # Cómo se compra. El costo por gramo NO se guarda: $1.200 la caja de 1 L de
    # leche son $1,2 el ml, y guardar "1" le quita un 17% al valor del
    # inventario. Se calcula con core.config.costo_de().
    formato: str = ""                     # "Caja 1 L", "Bolsa 1 kg", "Unidad"
    compra_contenido: int = 1             # cuántas unidades base trae el formato
    compra_costo: int = 0                 # CLP enteros que cuesta ese formato

    # De qué producto es "el mismo". Solo para lo que se compra y se vende TAL
    # CUAL: una botella, un alfajor, un pastel. Vacío en un insumo de verdad
    # (leche, café en grano), que alimenta varios productos y no es ninguno.
    #
    # Antes esto se resolvía comparando NOMBRES, y ahí estaba el bug que el
    # dueño encontró: "Coca-Cola 1.5 L" en la carta y "Coca Cola 1.5L" en la
    # bodega eran dos cosas distintas, así que se creaba un segundo insumo y el
    # stock del primero quedaba huérfano. Un id no se escribe mal.
    producto_id: Optional[int] = Field(default=None, foreign_key="producto.id", index=True)


class Ajuste(SQLModel, table=True):
    """Las preferencias del local. Una fila por decisión, en texto.

    Existe por el margen sugerido, y por qué no vive en el navegador: cuánto le
    gana el local a lo que vende es una decisión del NEGOCIO, no de este
    computador. Si viviera en el localStorage, se perdería al reinstalar y
    sería distinta abriendo la caja desde un tablet.

    El valor va como texto a propósito: así una preferencia nueva no obliga a
    una migración. Quien lee sabe qué esperaba y convierte.
    """
    clave: str = Field(primary_key=True)
    valor: str = ""


class CodigoBarra(SQLModel, table=True):
    """Un código de barras que apunta a un producto.

    Tabla aparte y no una columna en `Producto` porque **un producto tiene más
    de un código**, y en una botillería eso es el caso diario: la lata suelta y
    el pack de 6 traen códigos distintos y son el mismo trago. Lo mismo el vino
    que cambió de etiqueta y quedaron las dos en la bodega. Con una columna, ese
    caso queda afuera para siempre; con esta tabla cuesta lo mismo hoy.

    El código se guarda SIEMPRE normalizado a 13 dígitos: un UPC-A de 12 es un
    EAN-13 con un cero adelante, y guardarlos distinto significa tener el mismo
    producto duplicado según qué lector lo leyó.

    `cuantos` es cuántas unidades entrega ese código: 1 la lata, 6 el pack. Así
    el pack descuenta seis del mismo saldo sin ninguna tabla extra.
    """
    codigo: str = Field(primary_key=True)      # 13 dígitos, sin espacios
    producto_id: int = Field(foreign_key="producto.id", index=True)
    cuantos: int = 1
    nota: str = ""                             # "pack de 6", "etiqueta vieja"


class Receta(SQLModel, table=True):
    """Una fila = un ingrediente de un producto.

    No hay tabla cabecera porque la cabecera es el Producto. Un producto sin
    filas acá no mueve stock, y eso no es un error: es el estado normal el
    primer día, cuando todavía no se cargó ninguna receta.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    producto_id: int = Field(foreign_key="producto.id", index=True)
    insumo_id: int = Field(foreign_key="insumo.id", index=True)
    cantidad: int = 0                     # entera, en la unidad base del insumo


class Movimiento(SQLModel, table=True):
    """El libro del inventario. Fuente de verdad del stock.

    Solo se AGREGAN filas: nunca se edita ni se borra una, igual que VentaLinea.
    Es lo que permite contestar "¿por qué me faltan 3 litros de leche?", que es
    la única pregunta que el dueño hace de verdad. Una columna de saldo sola
    solo sabe contestar "te faltan".
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    insumo_id: int = Field(foreign_key="insumo.id", index=True)
    creado_at: datetime = Field(default_factory=ahora, index=True)
    tipo: str = "ajuste"                  # compra|venta|merma|ajuste|devolucion|carga

    # CON SIGNO: + entra, − sale. Un solo campo para que sea imposible escribir
    # un informe que sume las mermas como si entraran.
    cantidad: int = 0
    saldo_despues: int = 0                # cómo quedó el insumo después de esta fila
    costo: int = 0                        # lo que valía esa cantidad, CONGELADO

    motivo: str = ""                      # obligatorio en las mermas
    venta_id: Optional[int] = Field(default=None, foreign_key="venta.id", index=True)
    turno_id: Optional[int] = Field(default=None, foreign_key="turno.id")
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    hecho_por: str = ""                   # nombre copiado, como VentaLinea.nombre
