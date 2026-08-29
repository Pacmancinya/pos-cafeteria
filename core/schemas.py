"""Contratos de entrada y salida de la API (Pydantic v2)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from core.config import MARGEN_SUGERIDO, MEDIOS_PAGO, ROLES, UNIDADES


class LineaIn(BaseModel):
    producto_id: int
    cantidad: int = Field(default=1, ge=1, le=999)


class VentaIn(BaseModel):
    lineas: list[LineaIn]
    medio_pago: str = "efectivo"
    descuento: int = Field(default=0, ge=0)
    propina: int = Field(default=0, ge=0)
    nota: str = ""
    paga_con: Optional[int] = None      # solo para calcular el vuelto; no se guarda

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


class ProductoIn(BaseModel):
    categoria_id: int
    nombre: str
    descripcion: str = ""
    precio: int = Field(default=0, ge=0)
    activo: bool = True
    orden: int = 0
    destacado: bool = False
    badge: str = ""
    antes: Optional[int] = None
    etiqueta: str = ""
    dibujo: str = "mug"
    color: str = ""


class CategoriaIn(BaseModel):
    nombre: str
    orden: int = 0
    activa: bool = True


# ---------------------------------------------------------------- usuarios
class UsuarioIn(BaseModel):
    nombre: str
    rol: str = "cajero"
    # Vacío al editar significa "déjale el PIN que ya tenía": obligar a
    # reescribirlo para cambiarle el nombre a alguien termina en PINs de 1111.
    pin: str = ""
    activo: bool = True
    color: str = ""
    orden: int = 0

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


class AjustesIn(BaseModel):
    """Las preferencias del local. Solo lo que hoy se puede cambiar."""
    # 100% de margen es un precio infinito, y sobre 95 el sugerido se dispara
    # tanto que deja de ser una sugerencia. El tope es para que la pantalla no
    # muestre un disparate, no para decirle al dueño cuánto ganar.
    margen_sugerido: int = Field(default=MARGEN_SUGERIDO, ge=0, le=95)
