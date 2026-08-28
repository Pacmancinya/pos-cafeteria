# Boleta electrónica (SII) — lo que falta para conectarla

> **Estado: `[ROADMAP]`.** No está construido y no bloquea nada: el punto de venta
> registra ventas y cuadra caja sin emitir boleta. Este documento existe para que el día
> que se conecte no haya que rehacer nada ni inventar datos hacia atrás.
>
> Última revisión: 28-08-2026.

---

## 1. Qué documento corresponde

Una cafetería que vende al público final emite **boleta electrónica afecta a IVA**, que en
la nomenclatura del SII es el **DTE tipo 39**. (El tipo 41 es la boleta exenta; en una
cafetería normal no aplica, salvo que se vendan productos exentos.)

La boleta electrónica es **obligatoria** para todos los contribuyentes desde enero de 2021
(Ley 21.210). O sea: esto no es opcional, y si el local hoy emite boletas de alguna forma,
ya tiene resuelta buena parte de lo que sigue.

## 2. Lo que el local necesita tener (no es cosa del programa)

Estas cuatro cosas son del contribuyente, no del software. Sin ellas no hay boleta
electrónica, con cualquier sistema:

1. **Certificado digital.** Es la identidad electrónica con la que se firma cada
   documento. Se emite a nombre de una **persona natural** (el representante legal o un
   apoderado), es un archivo `.pfx`, se compra a una entidad acreditada por el SII y
   **vence**: si caduca, no se puede firmar nada hasta renovarlo.
2. **Estar inscrito como facturador electrónico** ante el SII.
3. **Folios (CAF).** Un archivo XML firmado por el SII que autoriza un rango de folios para
   un tipo de documento. Se piden al SII, son limitados, y **se consumen en orden
   secuencial**: no se pueden saltar ni reutilizar.
4. **Los datos del local:** RUT, giro y dirección.

## 3. Por dónde emitir: las dos opciones reales

**a) El portal gratuito del SII (MIPYME).** Existe y es gratis. Su límite es que **cada
documento se emite a mano**: no se puede automatizar ni conectar con la caja. Para un local
con cola en el mostrador no sirve — significaría que alguien tipea cada boleta dos veces.

**b) Un proveedor con API.** Es el camino para que la caja emita sola. Los que tienen API
documentada y se usan en Chile: **Bsale**, **Nubox**, **LibreDTE** (con API Gateway),
**BaseAPI**, **Haulmer**. Los precios que se ven publicados van del orden de **$10.000 a
$80.000 mensuales** según el plan y el volumen.

> ⚠️ Los precios y los planes cambian. Antes de decidir hay que cotizar, no fiarse de esta
> lista.

## 4. La pregunta que hay que contestar primero

**¿Con qué emite boletas la cafetería HOY?**

De la respuesta sale todo lo demás:

- **Si ya usa Bsale / Nubox / otro** → lo más barato y rápido es conectarse a *ese* mismo
  proveedor por su API. El local ya tiene certificado, folios y una cuenta andando; sería
  solo programar la llamada.
- **Si emite en el portal del SII a mano** → hay que elegir proveedor y contratarlo. Ahí
  conviene comparar, porque es un costo mensual nuevo.
- **Si todavía no emite boletas** → eso es un tema tributario que se resuelve con el
  contador antes de tocar el programa.

## 5. Qué le falta al modelo de datos

Lo que **ya está** y sirve tal cual:

- La venta es **inmutable**: se anula, no se edita (CONTRATO, decisión 5). Es exactamente
  lo que el SII espera de un documento emitido.
- Hay un **correlativo propio** (`Venta.numero`) desde 1.
- El **neto y el IVA** se calculan por diferencia y siempre suman el bruto exacto
  (decisión 1). Eso es lo que va en el documento.
- Cada línea congela **nombre, precio unitario, cantidad y subtotal**.
- Está el **medio de pago** y la fecha con zona horaria de Chile.

Lo que **falta capturar**, y cuándo conviene agregarlo:

| Qué | Dónde | Cuándo |
|---|---|---|
| RUT, giro y dirección del local | `core/config.py` | Ahora es una línea; sin esto no se puede emitir nada |
| Si un producto es **exento** de IVA | `Producto.exento` | Solo si la carta llega a tener productos exentos |
| Folio, tipo de DTE, estado y XML/PDF de cada venta | tabla `Boleta` nueva | Al conectar. `create_all` la crea sola |
| RUT del cliente | `Venta` | Solo si alguna vez piden **factura**, que es otro documento |

> El `folio` **no puede** ser `Venta.numero`. Son dos numeraciones distintas: la nuestra
> parte en 1 y es del local; la del SII viene en rangos autorizados por CAF. Mezclarlas es
> el error clásico y se paga caro.

La extensión ya está esbozada en `docs/CONTRATO.md`:

```
Boleta(id, venta_id→Venta, folio, tipo_dte, emitida_at, estado, xml_path, pdf_path)
```

Se agrega sin migración manual: `create_all` crea las tablas nuevas y `poner_al_dia()`
agrega las columnas que falten.

## 6. El comprobante que se imprime hoy

Dice **NO ES BOLETA** en un recuadro, y eso no es decorativo: mientras no haya emisión
electrónica, entregar un papel que se parezca a una boleta sin serlo deja expuesto al
local. Ese recuadro se saca **el mismo día** en que la boleta se emita de verdad, no antes.

Cuando eso pase, el papel además tendrá que llevar el folio, el timbre y los datos del
emisor que exija el formato del proveedor.

## 7. Para el contador

El resumen del día ya entrega **neto, IVA, total, propinas y descuentos**, y la exportación
a CSV trae el detalle. Eso alcanza para revisar y cuadrar.

Lo que **no** reemplaza es la declaración: el F29 se arma con los documentos emitidos ante
el SII, no con este informe. Mientras las boletas se emitan por fuera, el informe de la
caja y lo declarado son dos cosas separadas — y conviene que el contador las compare de
vez en cuando, porque la diferencia entre ambas es justamente donde aparecen las ventas que
no se boletearon.

## 8. Lo que NO se va a hacer acá

- **Firmar los DTE nosotros mismos.** Implica manejar el certificado, el timbraje, el envío
  al SII, los reintentos y el seguimiento del estado. Es un proyecto en sí mismo y ya
  existe gente que lo vende hecho y certificado.
- **Guardar el certificado digital dentro del programa.** Vive donde lo ponga el proveedor.

---

**Resumen en una línea:** falta que el dueño diga con qué emite boletas hoy. Con esa
respuesta, conectar la caja es trabajo acotado; sin ella, cualquier cosa que se construya
es adivinar.
