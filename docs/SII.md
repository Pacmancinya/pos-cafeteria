# Conectar la caja con el SII — guía

> Para emitir **boleta electrónica** desde el punto de venta.
> Escrita para el dueño del local; la parte técnica va al final.
>
> Estado: **no está construido todavía**, y no bloquea nada — la caja registra
> ventas y cuadra sin emitir boleta. Esta guía es para que el día que se decida,
> el camino esté claro y no haya que inventar datos hacia atrás.
>
> Última revisión: 28-08-2026.

---

## Lo primero: la pregunta que destraba todo

> ### ¿Con qué emite boletas la cafetería HOY?

De la respuesta sale todo lo demás. Hay tres casos y cada uno tiene un camino
distinto:

| Si hoy… | Lo que hay que hacer |
|---|---|
| **Ya usa Bsale, Nubox u otro** | Conectarse a **ese mismo** proveedor por su API. El local ya tiene certificado, folios y cuenta andando: sería solo programar la llamada. Es el camino más corto y no cuesta plata nueva. |
| **Emite en el portal del SII a mano** | Hay que elegir y contratar un proveedor con API. Acá sí hay un costo mensual nuevo, y conviene cotizar. |
| **Todavía no emite boletas** | Eso es un tema tributario, no de software. Se resuelve con el contador **antes** de tocar el programa. |

No sigas leyendo sin esa respuesta: los pasos de abajo cambian según cuál sea.

---

## Paso 1 — Junta estas cuatro cosas

Son del contribuyente, no del programa. Sin ellas no hay boleta electrónica con
**ningún** sistema, ni con el nuestro ni con uno comprado.

1. **Certificado digital.** Es la firma electrónica del local. Va a nombre de una
   **persona** (el representante legal o alguien con poder), es un archivo
   `.pfx`, se compra a una entidad autorizada por el SII y **vence**: si caduca,
   deja de emitir hasta renovarlo. Anota la fecha de vencimiento en el celular.
2. **Estar inscrito como facturador electrónico** ante el SII.
3. **Folios (CAF).** Es la autorización del SII para usar un rango de números de
   boleta. Se piden al SII, son limitados y **se usan en orden**: no se saltan ni
   se repiten. Hay que estar pendiente de que no se acaben.
4. **Los datos del local:** RUT, giro y dirección.

> Si el local ya emite boletas, **ya tiene las cuatro**. Pídeselas al contador.

---

## Paso 2 — Elige por dónde emitir

**a) El portal gratuito del SII (MIPYME).** Existe y no cuesta nada. Su límite es
que **cada boleta se emite a mano**, una por una, en el sitio del SII. Para un
local con gente esperando en el mostrador no sirve: significaría escribir cada
venta dos veces.

**b) Un proveedor con API.** Es lo que permite que la caja emita sola. Los que se
usan en Chile y tienen documentación para conectarse: **Bsale**, **Nubox**,
**LibreDTE**, **BaseAPI**, **Haulmer**. Los precios publicados van del orden de
**$10.000 a $80.000 mensuales** según el plan y cuántos documentos se emiten.

> ⚠️ Los precios y los planes cambian seguido. **Cotiza antes de decidir**, no te
> quedes con esta lista.

**Qué preguntarle a cada proveedor**, para comparar de verdad:

- ¿Tiene API para emitir **boleta electrónica (DTE 39)**, no solo factura?
- ¿El plan incluye los documentos que emitimos al mes, o se cobran aparte?
- ¿Se encargan del certificado y de pedir los folios, o eso lo hago yo?
- ¿Qué pasa si se cae su servicio en hora punta? ¿Puedo seguir vendiendo?
- ¿Me entregan el XML y el PDF de cada boleta, o quedan solo en su sistema?

---

## Paso 3 — Qué hay que decidir antes de programar

Tres decisiones del dueño, no del programador:

1. **¿Boleta a todos, o solo a quien la pide?** Legalmente corresponde emitirla
   siempre. En la práctica cambia mucho el flujo del mostrador; conviene hablarlo
   con el contador.
2. **¿Se imprime o se manda?** Se puede imprimir en la misma impresora de 80 mm,
   o mandarla por correo o QR. Lo segundo ahorra papel y necesita pedirle el dato
   al cliente.
3. **¿Qué pasa si se cae internet?** Es el caso que más importa y el que más se
   olvida. La caja tiene que **seguir vendiendo** igual, y emitir después las
   boletas que quedaron pendientes. Eso se construye a propósito; no sale gratis.

---

## Paso 4 — Lo que hay que capturar desde ya

Esto es lo que hace que conectar después sea barato. Lo que **ya está bien**:

- La venta es **inmutable**: se anula, no se edita. Es exactamente lo que el SII
  espera de un documento emitido.
- Hay un **correlativo propio** desde 1.
- El **neto y el IVA** salen exactos y siempre suman el total.
- Cada línea guarda **nombre, precio, cantidad y subtotal** congelados.
- Queda la fecha con hora de Chile y el medio de pago.

Lo que **falta**, y cuándo agregarlo:

| Qué | Cuándo |
|---|---|
| RUT, giro y dirección del local | **Ahora**: es una línea en `core/config.py` y sin eso no se puede emitir nada |
| Marcar si un producto es **exento** de IVA | Solo si la carta llega a tener productos exentos |
| Folio, tipo de documento, estado y XML/PDF por venta | Al conectar. Es una tabla nueva y se crea sola |
| RUT del cliente | Solo si alguna vez piden **factura**, que es otro documento |

> **El folio del SII no es el número de venta del POS.** Son dos numeraciones
> distintas: la nuestra parte en 1 y es del local; la del SII viene en rangos
> autorizados. Mezclarlas es el error clásico y se paga caro.

---

## Paso 5 — Lo que va a cambiar en la caja

- El comprobante que hoy dice **NO ES BOLETA** deja de decirlo. Ese recuadro se
  saca **el mismo día** en que la boleta se emita de verdad, no antes: mientras
  tanto, entregar un papel parecido a una boleta sin serlo deja expuesto al local.
- El papel pasa a llevar el folio, el timbre y los datos del emisor.
- Aparece un lugar para ver las boletas que quedaron pendientes de enviar.

---

## Para el contador

El resumen del día ya entrega **neto, IVA, total, propinas y descuentos**, y la
exportación a CSV trae el detalle venta por venta. Eso alcanza para revisar.

Lo que **no** reemplaza es la declaración: el F29 se arma con los documentos
emitidos ante el SII, no con este informe. Mientras las boletas se emitan por
fuera, el informe de la caja y lo declarado son dos cosas separadas — y conviene
compararlas de vez en cuando, porque **la diferencia entre ambas es justamente
donde aparecen las ventas que no se boletearon**.

---

## Parte técnica

Documento: **DTE tipo 39** (boleta electrónica afecta a IVA); el 41 es la exenta.
Obligatorio para todos los contribuyentes desde enero de 2021 (Ley 21.210).

La extensión ya está esbozada en [`CONTRATO.md`](CONTRATO.md):

```
Boleta(id, venta_id→Venta, folio, tipo_dte, emitida_at, estado, xml_path, pdf_path)
```

Se agrega sin migración manual: `create_all` crea las tablas nuevas y
`poner_al_dia()` agrega las columnas que falten.

**Lo que NO se va a hacer acá:**

- **Firmar los DTE nosotros mismos.** Implica manejar el certificado, el
  timbraje, el envío al SII, los reintentos y el seguimiento de estado. Es un
  proyecto en sí mismo y ya hay gente que lo vende hecho y certificado.
- **Guardar el certificado digital dentro del programa.** Vive donde lo ponga el
  proveedor.

**El punto delicado del diseño** va a ser el modo sin internet: la venta se
registra siempre, y la emisión queda en una cola que se reintenta. Eso obliga a
que `Boleta.estado` distinga *pendiente / emitida / rechazada* y a que haya una
pantalla donde se vean las rechazadas — porque una boleta rechazada que nadie
mira es una venta sin documento.
