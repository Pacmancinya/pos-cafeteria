"""Contratos de entrada y salida de la API (Pydantic v2)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from core.codigos import FORMATO_BALANZA_POR_DEFECTO, validar_formato_balanza
from core.config import (BLOQUEO_MINUTOS, MARGEN_SUGERIDO, MEDIOS_PAGO, ROLES,
                         TECLADO_EN_PANTALLA, TODOS_LOS_PERMISOS, UNIDADES)


class LineaIn(BaseModel):
    """Una línea del pedido: un producto de la carta, o un cobro a mano.

    El cobro a mano existe porque en el mostrador siempre aparece algo que no está en la
    carta. Es la única línea cuyo precio llega desde la pantalla en vez de salir del
    catálogo, así que pide su propio permiso y queda firmada con quién la cobró.
    """
    producto_id: Optional[int] = None
    cantidad: int = Field(default=1, ge=1, le=999)
    # Solo para el cobro a mano. Con `precio` puesto, la línea es "varios".
    nombre: str = Field(default="", max_length=60)
    precio: Optional[int] = Field(default=None, ge=0, le=99_000_000)

    @model_validator(mode="after")
    def producto_o_monto(self):
        if self.producto_id is None and self.precio is None:
            raise ValueError("Una línea lleva un producto de la carta o un monto a mano.")
        return self


class PagoIn(BaseModel):
    """Una parte de un pago mixto: cuánto se pagó con este medio."""
    medio: str
    monto: int = Field(gt=0)

    @field_validator("medio")
    @classmethod
    def medio_valido(cls, v):
        if v not in MEDIOS_PAGO:
            raise ValueError(f"Medio de pago desconocido: {v}")
        return v


class VentaIn(BaseModel):
    lineas: list[LineaIn]
    medio_pago: str = "efectivo"
    descuento: int = Field(default=0, ge=0)
    propina: int = Field(default=0, ge=0)
    nota: str = ""
    paga_con: Optional[int] = None      # solo para calcular el vuelto; no se guarda
    # Pago mixto: parte en efectivo, parte en otra forma. Si viene, manda sobre
    # `medio_pago` y la suma tiene que dar lo cobrado. Vacío = un solo medio,
    # como siempre.
    pagos: list[PagoIn] = Field(default_factory=list)

    @field_validator("lineas")
    @classmethod
    def no_vacia(cls, v):
        if not v:
            raise ValueError("La venta no puede ir sin productos")
        return v

    @field_validator("medio_pago")
    @classmethod
    def medio_valido(cls, v):
        if v not in MEDIOS_PAGO:
            raise ValueError(f"Medio de pago desconocido: {v}")
        return v


class AnularIn(BaseModel):
    motivo: str = ""


class RetiroCajaIn(BaseModel):
    """Sacar plata del cajón en medio del turno. El motivo es obligatorio: un
    retiro sin motivo no se distingue de un faltante."""
    monto: int = Field(gt=0)
    motivo: str

    @field_validator("motivo")
    @classmethod
    def con_motivo(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("Escribe para qué sacas la plata (gas, pan, etc.).")
        return v


class AbrirTurnoIn(BaseModel):
    cajero: str = ""
    monto_inicial: int = Field(default=0, ge=0)
    # Si viene el conteo por denominación, manda él y monto_inicial se calcula.
    conteo: dict[str, int] = Field(default_factory=dict)


class CerrarTurnoIn(BaseModel):
    efectivo_contado: int = Field(default=0, ge=0)
    conteo: dict[str, int] = Field(default_factory=dict)
    retiro: int = Field(default=0, ge=0)
    fondo_siguiente: int = Field(default=0, ge=0)
    nota: str = ""
    # Lo que dice el comprobante de cierre de la máquina y la app del banco,
    # por medio de pago: {"debito": 123400, "transferencia": 20000}.
    medios: dict[str, int] = Field(default_factory=dict)
    # Lo que la máquina dice que fueron las PROPINAS, por medio de pago.
    propinas_medios: dict[str, int] = Field(default_factory=dict)
    # Cuánto de la propina de tarjeta se le pagó al equipo en efectivo, sacado
    # del cajón esta misma noche.
    propinas_pagadas: int = Field(default=0, ge=0)


class ProductoIn(BaseModel):
    categoria_id: int
    nombre: str
    descripcion: str = ""
    precio: int = Field(default=0, ge=0)
    plu: str = ""
    precio_kilo: int = Field(default=0, ge=0, le=9223372036854775807, strict=True)
    activo: bool = True
    orden: int = 0
    destacado: bool = False
    badge: str = ""
    antes: Optional[int] = None
    etiqueta: str = ""
    dibujo: str = "mug"
    color: str = ""

    # ---- lo que antes obligaba a ir a la Bodega ----
    # Estos campos existen para que crear un producto sea UN solo formulario.
    # Antes había que crearlo en la carta, ir a la bodega, crearlo otra vez con
    # el mismo nombre escrito a mano, y recién ahí amarrarlos. La base del local
    # lo demuestra: 148 ventas y UN insumo cargado. No es que el inventario no
    # importe — es que entrar costaba más de lo que daba.
    codigo: str = ""                       # el de barras, si lo escaneó
    tal_cual: bool = False                 # se compra y se vende igual: es su propio insumo
    llevar_cuenta: bool = False
    costo: int = Field(default=0, ge=0)    # cuánto cuesta cada uno
    stock_inicial: int = Field(default=0, ge=0)
    minimo: int = Field(default=0, ge=0)   # bajo esto aparece en "Por comprar"


class CategoriaIn(BaseModel):
    nombre: str
    orden: int = 0
    activa: bool = True

    @field_validator("nombre")
    @classmethod
    def con_nombre(cls, v):
        # Sin esto una pantalla de editar podía dejar una categoría llamada "   ",
        # que en el rail es un botón sin texto imposible de distinguir del de al
        # lado. El prompt() viejo filtraba el vacío; el editor nuevo no.
        v = (v or "").strip()
        if not v:
            raise ValueError("Escribe un nombre para la categoría.")
        return v


# ---------------------------------------------------------------- usuarios
class UsuarioIn(BaseModel):
    nombre: str
    rol: str = "cajero"
    # Vacío hereda el rol; al editar, omitir el campo conserva lo guardado.
    permisos: str = ""
    # Vacío al editar significa "déjale el PIN que ya tenía": obligar a
    # reescribirlo para cambiarle el nombre a alguien termina en PINs de 1111.
    pin: str = ""
    activo: bool = True
    color: str = ""
    orden: int = 0

    @field_validator("permisos")
    @classmethod
    def permisos_validos(cls, v):
        claves = {p.strip() for p in v.split(",") if p.strip()}
        if claves - set(TODOS_LOS_PERMISOS):
            raise ValueError("Hay permisos que no existen. Vuelve a abrir la persona y elige de la lista.")
        return ",".join(p for p in TODOS_LOS_PERMISOS if p in claves)

    @field_validator("nombre")
    @classmethod
    def con_nombre(cls, v):
        if not v.strip():
            raise ValueError("El usuario necesita un nombre")
        return v.strip()

    @field_validator("rol")
    @classmethod
    def rol_valido(cls, v):
        if v not in ROLES:
            raise ValueError(f"Rol desconocido: {v}")
        return v

    @field_validator("pin")
    @classmethod
    def pin_de_cuatro(cls, v):
        if v and (len(v) < 4 or not v.isdigit()):
            raise ValueError("El PIN son 4 números o más")
        return v


class EntrarIn(BaseModel):
    usuario_id: int
    pin: str = ""


class SalirIn(BaseModel):
    # cambio = se cambió de usuario · bloqueo = se bloqueó sola · salir = botón
    por: str = "salir"


# ---------------------------------------------------------------- inventario
class InsumoIn(BaseModel):
    nombre: str
    unidad: str = "un"
    minimo: int = Field(default=0, ge=0)
    formato: str = ""
    compra_contenido: int = Field(default=1, ge=1)
    compra_costo: int = Field(default=0, ge=0)
    activo: bool = True
    orden: int = 0
    # Solo se usa al crear: escribe el movimiento de carga inicial.
    stock_inicial: int = Field(default=0, ge=0)

    @field_validator("nombre")
    @classmethod
    def con_nombre(cls, v):
        if not v.strip():
            raise ValueError("El insumo necesita un nombre")
        return v.strip()

    @field_validator("unidad")
    @classmethod
    def unidad_valida(cls, v):
        if v not in UNIDADES:
            raise ValueError(f"Unidad desconocida: {v}. Van en {', '.join(UNIDADES)}")
        return v


class LineaRecetaIn(BaseModel):
    insumo_id: int
    cantidad: int = Field(ge=1)


class RecetaIn(BaseModel):
    lineas: list[LineaRecetaIn] = Field(default_factory=list)


class CantidadBodegaIn(BaseModel):
    cantidad: int = Field(ge=0, le=2147483647, strict=True)
    stock_esperado: int = Field(strict=True)
    motivo: Literal["llego", "se perdio", "conteo", "ajuste"]


class TalCualIn(BaseModel):
    """El atajo del día 1: convierte un producto en su propio insumo."""
    stock_inicial: int = Field(default=0, ge=0)
    minimo: int = Field(default=0, ge=0)
    compra_costo: int = Field(default=0, ge=0)


class CompraIn(BaseModel):
    insumo_id: int
    envases: int = Field(default=1, ge=1)
    compra_costo: Optional[int] = Field(default=None, ge=0)
    motivo: str = ""


class MermaIn(BaseModel):
    insumo_id: int
    cantidad: int = Field(ge=1)
    # Sin valor por defecto A PROPÓSITO: con default, el validador de abajo no
    # corre cuando el campo no viene, y una merma sin motivo pasaba derecho.
    motivo: str

    @field_validator("motivo")
    @classmethod
    def con_motivo(cls, v):
        # Una merma sin motivo no se distingue de un faltante.
        if not v.strip():
            raise ValueError("Escribe qué pasó: se cayó, se venció, se probó…")
        return v.strip()


class ConteoIn(BaseModel):
    """{"3": 4000, "7": 12} — lo que se contó de verdad, por insumo."""
    conteos: dict[str, int] = Field(default_factory=dict)
    nota: str = ""


# ---------------------------------------------------------------- importar
class TextoImportadoIn(BaseModel):
    texto: str = ""


class ProductoImportadoIn(BaseModel):
    """Una fila ya revisada por la persona en la pantalla, no el archivo crudo."""
    nombre: str
    precio: int = Field(default=0, ge=0)
    categoria: str = "Carta"
    descripcion: str = ""
    dibujo: str = "mug"


class AplicarImportacionIn(BaseModel):
    productos: list[ProductoImportadoIn] = Field(default_factory=list)
    # Saca de la venta lo que la caja tenía y el archivo no trae. Va aparte y
    # en falso por defecto: un archivo incompleto no puede borrar una carta.
    sacar_lo_que_no_vino: bool = False


class PlanCierreIn(BaseModel):
    """Lo contado en el cajón y cuánto hay que apartar, para que la caja diga QUÉ apartar.

    Las claves de `conteo` llegan como texto desde la web (JSON no tiene claves enteras);
    el validador las pasa a número para no ensuciar el resto con esa conversión.
    """
    conteo: dict[int, int] = Field(default_factory=dict)
    propina: int = Field(default=0, ge=0)
    fondo: int = Field(default=0, ge=0)

    @field_validator("conteo", mode="before")
    @classmethod
    def claves_enteras(cls, v):
        if not isinstance(v, dict):
            return {}
        salida: dict[int, int] = {}
        for den, cant in v.items():
            try:
                den, cant = int(den), int(cant)
            except (TypeError, ValueError):
                continue
            # Un billete de más de un millón no existe; una denominación absurda solo puede
            # venir de un error, y aceptarla haría trabajar a la caja para nada.
            if not (0 < den <= 1_000_000) or cant <= 0:
                continue
            # SUMAR y no reemplazar: "1000" y "01000" son la misma moneda, y la pantalla
            # puede mandar las dos. Reemplazando se perdían piezas contadas a mano — la
            # cuenta decía 3.000 cuando habían llegado 5.000.
            salida[den] = salida.get(den, 0) + cant
        return salida


class AjustesIn(BaseModel):
    """Las preferencias del local. Solo lo que hoy se puede cambiar."""
    usar_inventario: int = Field(default=1, ge=0, le=1)
    # 100% de margen es un precio infinito, y sobre 95 el sugerido se dispara
    # tanto que deja de ser una sugerencia. El tope es para que la pantalla no
    # muestre un disparate, no para decirle al dueño cuánto ganar.
    margen_sugerido: int = Field(default=MARGEN_SUGERIDO, ge=0, le=95)
    # 0 o 1. En un notebook con teclado, el teclado dibujado estorba; en una
    # pantalla táctil es lo único con lo que se puede escribir.
    teclado_en_pantalla: int = Field(default=int(TECLADO_EN_PANTALLA), ge=0, le=1)
    # Entre 1 y 30 minutos: menos que eso bloquea en medio de atender, y más
    # deja una sesión abierta que ya no dice la verdad sobre quién estuvo.
    bloqueo_minutos: int = Field(default=BLOQUEO_MINUTOS, ge=1, le=30)
    canal_actualizaciones: Literal["estable", "piloto"] = "estable"
    # La carpeta de la copia de afuera. Vacía = no hay copia de afuera.
    respaldo_afuera: str = Field(default="", max_length=300)
    formato_balanza: dict = Field(
        default_factory=lambda: validar_formato_balanza(FORMATO_BALANZA_POR_DEFECTO))

    @field_validator("formato_balanza", mode="before")
    @classmethod
    def formato_valido(cls, v):
        return validar_formato_balanza(v)


class CodigoIn(BaseModel):
    """Un código de barras que se le pega a un producto."""
    codigo: str
    # Cuántas unidades entrega este código: 1 la lata, 6 el pack. Es lo que hace
    # que el pack descuente seis del mismo saldo sin ninguna tabla extra.
    cuantos: int = Field(default=1, ge=1, le=999)
    nota: str = ""
