# Boleta electrónica — etapa 1, con Lioren

> Decisión del 23-09-2026: la boleta parte con un proveedor, el más barato con API, y
> después pasa a software propio ([BOLETA-ELECTRONICA.md](BOLETA-ELECTRONICA.md)). El
> proveedor elegido es **Lioren** (lioren.cl), por tres razones:
>
> 1. **Es el más barato para un local chico**: se paga por módulo (boleta y nota de
>    crédito, 0,1 UF al mes cada uno) más 0,0002 UF por boleta emitida por la API.
> 2. **La caja pone el timbre.** Lioren entrega los folios (CAF) por su API; la caja
>    timbra cada boleta y Lioren arma el XML, lo firma con el certificado del local y lo
>    envía al SII. Así la caja puede emitir **sin internet** y mandar después, dentro de
>    la hora que da la Res. Ex. SII 74 de 2020 (F.6) desde que vuelve la conexión.
> 3. **Lo que se construye sirve para la etapa 2**: folios, timbre, cola y estados son
>    los mismos; en la etapa 2 solo se reemplaza «Lioren firma y envía» por «la caja firma
>    y envía».
>
> `[ROADMAP]`: no construido todavía.

---

## Lo que dice la API de Lioren

Documentación: <https://www.lioren.cl/docs>. Se autentica con un token personal de la
empresa (`Authorization: Bearer ...`), que se genera en su panel y no se puede volver a
ver. Prueba de conexión: `GET https://www.lioren.cl/api/whoami`.

| Qué | Ruta | Notas |
|---|---|---|
| Pedir folios | `POST /api/cafs` con `tipodoc` y `cantidad` (hasta 10.000) | Devuelve el CAF en XML (base64). Sin costo. |
| Ver un CAF | `GET /api/cafs/{id}` | Mismo contenido. |
| Emitir boleta | `POST /api/boletas` | **Obligatorios: `folio`, `fecha` y `ted64` (el TED ya firmado, en base64)**, `servicio=3`, `detalles` (hasta 60 líneas, precio BRUTO). Receptor opcional. `expects=xml|pdf|all` para que devuelva el documento. Costo 0,0002 UF. |
| Consultar boleta | `GET /api/boletas?tipodoc=39&folio=N&expects=xml` | Para reconciliar después de un corte. |
| Nota de crédito | `POST /api/dtes` con `tipodoc=61` y una referencia a la boleta | Acá no se pide `ted64`: la numera y timbra Lioren, así que **necesita internet**. Anular no es urgente: puede esperar. |

Requisito de Lioren: la empresa registrada en su plataforma y enrolada ante el SII como
facturador electrónico con Lioren como software de mercado. Eso lo hace el dueño del
local, no nosotros.

---

## Cómo queda el flujo en la caja

1. **Al configurar el local** (una vez): el dueño pega el token de Lioren en Configurar.
   La caja pide un CAF de boletas (`tipodoc=39`) y lo guarda. El token y el CAF se
   guardan fuera del árbol que reemplaza el actualizador, protegidos con DPAPI (ver
   BOLETA-ELECTRONICA.md, sección 6).
2. **Al cobrar**: la caja reserva el siguiente folio (reserva atómica en SQLite), arma el
   `DD` del TED y lo firma con la llave del CAF (RSA-SHA1, PKCS#1 v1.5). **Esto va en
   Python puro, sin PowerShell**: la venta no puede esperar un proceso aparte, y el
   cálculo es chico (`hashlib` + `pow`). Guarda el documento como *pendiente* e imprime.
3. **Enseguida, en segundo plano**: la cola manda `POST /api/boletas`. Si responde bien,
   queda *enviada* y guarda el XML. Si no hay internet, reintenta; al volver la conexión
   vacía la cola antes de una hora.
4. **Folios**: avisa cuando quedan pocos para unos días de venta y pide otro CAF por la
   API. Un folio reservado nunca se reutiliza.
5. **Anular**: nota de crédito por `POST /api/dtes`, cuando haya internet.

La opción del voucher (A: el voucher de tarjeta vale como boleta; B: boleta siempre) es
una configuración del local con fecha de vigencia, igual que en la etapa 2 (sección 7 de
BOLETA-ELECTRONICA.md).

---

## Fases

| Fase | Días | Qué |
|---|---:|---|
| 1 | 2 | Leer y validar un CAF; armar y firmar el TED en Python puro, con pruebas contra una llave y un CAF de prueba hechos por nosotros. |
| 2 | 3 | Documento por venta, reserva de folios, cola, estados y reintentos, con un Lioren de mentira en las pruebas. |
| 3 | 2 | Cliente de Lioren (token, CAF, boleta, consulta, nota de crédito) y guardar secretos con DPAPI. |
| 4 | 2 | Pantallas: token y folios en Configurar, estado de la cola, lo rechazado; el comprobante deja de decir «NO ES BOLETA» y pasa a decir folio y «Boleta electrónica». |
| 5 | 2 | Prueba de punta a punta con la cuenta real del local y puesta en marcha en el piloto. |

---

## Pendiente de confirmar con Lioren

- Si tienen ambiente de pruebas; si no, cómo probar sin emitir boletas reales.
- Si los precios son más IVA y si el cargo de 0,0002 UF por boleta aplica siempre por la
  API (su página de precios lo menciona para tiendas en línea).
- Cómo validan el `ted64` que les mandamos y qué responden si llega con un folio ya usado.
- Si aceptan boletas con fecha de horas antes (las que quedaron en cola por un corte).
