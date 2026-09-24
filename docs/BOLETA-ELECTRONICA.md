# Boleta electrónica — diseño de implementación

> **Decisión del 23-09-2026: software propio, sin proveedor externo de emisión.**
> `[ROADMAP]`: diseñado, todavía no construido ni certificado. Este documento guía la
> implementación y supera el camino con proveedor descrito en [SII.md](SII.md).
>
> Base: investigación técnica de fase 0. Las decisiones de diseño se expresan como lo
> que se construirá; no son funciones disponibles hoy. Los contratos externos y las
> compatibilidades que aún faltan por comprobar llevan la marca **sin verificar**.
> Los ejemplos son ficticios; los datos y secretos de cada contribuyente quedan fuera
> de este repositorio público.

## 1. Qué se va a construir y por qué

La caja emitirá boletas afectas **39** y notas de crédito **61** para corregirlas.
Se conectará directamente al SII. Nos hacemos cargo del XML, firmas, folios, envío,
seguimiento y consulta pública: permite controlar la emisión local y recuperarla sin
depender de la API de un proveedor. También nos deja a cargo de mantener la integración
cuando cambien los formatos o las reglas del SII.

**Cada local, a través de su contribuyente, certificará con nuestro software.** El
proceso contempla solicitar el set de pruebas, emitir y enviar los casos, presentar
muestras y tener disponible el sitio de consulta. Después vienen la revisión, la
declaración de cumplimiento y la autorización. El contribuyente debe estar autorizado
como emisor electrónico o estar certificándose en paralelo. La guía indica **10 a 15
días hábiles de revisión**; no es la duración garantizada del proceso completo.
[Guía de certificación del SII](https://www.sii.cl/factura_electronica/guia_emitir_boleta_servicio.htm).

Este será el camino hasta obtener autorización como proveedor del producto. Para
solicitarla, el SII exige cumplir la Res. 74, haber habilitado al menos **10
contribuyentes mediante certificación automática** desde el 01-07-2020 y contar con
**6 meses de experiencia emitiendo**. Cumplir esos mínimos no da autorización por sí
solo. [Requisitos para proveedores](https://www.sii.cl/servicios_online/3785-.html).

«Software propio» significa que desarrollamos el producto; no que cada contribuyente
sea su autor. Quién figurará en `RutProvSW` y `RznSocProvSW` mientras la empresa del
producto no tenga RUT propio está **sin verificar**. No se inventará un RUT ni se
marcará al local como desarrollador para llenar el campo.

El alcance inicial no incluye facturas ni boletas exentas 41. Tampoco se construirá el
Resumen de Ventas Diarias (RVD): su obligación se eliminó desde agosto de 2022, aunque
las guías antiguas todavía lo mencionen.
[FAQ del SII sobre RVD](https://www.sii.cl/preguntas_frecuentes/bol_electr_vtas_serv/001_380_7455.htm).

## 2. Reparto entre Python y Windows

| Pieza | Responsable |
|---|---|
| Venta, pagos y cálculo tributario congelado por documento | Python existente |
| Reserva de folios, persistencia, colas, reintentos y estados | Python + SQLite |
| Bytes finales del XML y validación XSD | .NET: `XmlDocument` y `XmlSchemaSet` |
| Certificado PFX y firma XMLDSig | .NET: `X509Certificate2` y `SignedXml` |
| Firma del TED con la llave del CAF | RSA de .NET |
| Protección local de secretos | .NET: DPAPI `CurrentUser` |
| HTTP al SII y al sitio de consulta | Python; `urllib`, sujeto a probar el exe instalado |

**No se agregan dependencias al exe instalado.** La investigación no encontró
`cryptography` ni `lxml` en `Kofe.exe`; una actualización de código no agrega librerías
a `_internal`. Incluso los módulos de biblioteca estándar deben comprobarse en el exe
más antiguo. El inventario completo de ese ejecutable sigue **sin verificar**.

Se usará **Windows PowerShell 5.1**, con un script fijo embebido en un `.py`, proceso
oculto y datos JSON por **stdin**, siguiendo
[`apps/pos/impresion_windows.py`](../apps/pos/impresion_windows.py). No se interpolarán
datos en comandos. Contraseñas, llaves y tokens no irán en argumentos, logs ni errores.
Python entregará datos estructurados; .NET devolverá los bytes firmados en Base64 y un
resultado estructurado. Python los decodificará y guardará sin volver a serializar XML.

Los XSD viajarán como texto en `.txt` o cadenas de `.py`, extensiones que
[`actualizar.py`](../apps/pos/actualizar.py) ya copia. Hoy no copia `.ps1`, `.dll` ni
`.xsd`. Se fijarán versión y huella de los esquemas y sus dependencias; .NET resolverá
los imports desde esos recursos, sin descargar esquemas al emitir ni resolver entidades
externas. No hace falta cambiar el actualizador para transportar esos archivos.

`ElementTree.canonicalize()` usa **C14N 2.0** y no reemplaza la C14N 1.0 de este perfil.
Por eso .NET construye y firma el XML final. Se partirá con un proceso por operación y
se medirá la latencia antes de considerar un proceso persistente.
[ElementTree](https://docs.python.org/3/library/xml.etree.elementtree.html),
[SignedXml](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.xml.signedxml).

## 3. Documentos, timbre y firmas

La investigación revisó el **formato de boletas 4.2 (08-09-2025)** y el **formato DTE 2.5
(febrero de 2026)**. Son versiones de manuales, no el atributo `version` del XML.
El juego exacto de XSD vigente, con orden, cardinalidades y dependencias, está **sin
verificar**. Estos campos orientan el generador; no reemplazan el esquema completo.

| Documento | Datos principales |
|---|---|
| Boleta 39 | `TipoDTE`, `Folio`, `FchEmis`, `IndServicio=3` para el caso de venta definido; `RUTEmisor`, `RznSocEmisor`, `GiroEmisor`, dirección y comuna; `RUTRecep`; `MntNeto`, `IVA`, `MntTotal`; detalle con nombre, cantidad, precio y monto. |
| Nota 61 | Folio propio de CAF 61; emisor con `RznSoc`, `GiroEmis`, `Acteco`; receptor identificado según el caso; totales y detalle de la corrección; referencia con `TpoDocRef=39`, `FolioRef`, `FchRef`, `CodRef` y razón. |
| Carátula | Emisor, firmante, receptor SII, resolución del contribuyente y ambiente, fecha de firma del envío y subtotales por tipo. Ningún dato real se fija en el código. |

En boletas, los precios son brutos salvo uso de `IndMntNeto=2`; descuentos e indicadores
tributarios se informan cuando corresponda. El receptor no identificado sigue las
condiciones del formato. Sobre 135 UF se exige identificar al comprador y el medio de
pago, además de describir los productos. Es una validación previa a emitir, no un campo
que se completa después.
[Formato de boletas](https://www.sii.cl/factura_electronica/factura_mercado/formato_boleta_electronica.pdf).

En notas, `CodRef=1` anula, `2` corrige texto y `3` corrige montos. No se convierte una
devolución en líneas negativas indiscriminadamente. Para precios brutos existe
`MntBruto=1`; no se copia `IndMntNeto` de la boleta. Tampoco se copia automáticamente
su receptor genérico: usar al propio emisor como receptor es una excepción cuando no
se logran obtener los datos del comprador.
[Formato DTE 2.5](https://www.sii.cl/factura_electronica/factura_mercado/formato_dte_202602.pdf),
[FAQ sobre receptor de la nota](https://www.sii.cl/preguntas_frecuentes/bol_electr_vtas_serv/001_380_6571.htm).

**Dos sobres y dos adaptadores.** La boleta se envuelve en `EnvioBOLETA`; la nota 61 va
por el circuito DTE general, en `EnvioDTE`, con autenticación, envío y consultas propios.
No se supone que la API de boletas acepte notas. En ambos casos hay `SetDTE`, carátula y
documentos `DTE`; cada `Documento` lleva su firma y el conjunto lleva otra.
Espacios de nombres: `http://www.sii.cl/SiiDte` y `http://www.w3.org/2000/09/xmldsig#`.

| XMLDSig | Perfil que se implementará |
|---|---|
| Canonicalización de `SignedInfo` y transformación de referencia | C14N 1.0 inclusiva, sin comentarios: `http://www.w3.org/TR/2001/REC-xml-c14n-20010315` |
| Digest | SHA1: `http://www.w3.org/2000/09/xmldsig#sha1` |
| Firma | RSA-SHA1: `http://www.w3.org/2000/09/xmldsig#rsa-sha1` |
| `KeyInfo` | `RSAKeyValue` con módulo y exponente, y certificado público DER en Base64 en `X509Data` |

Primero se firma `Documento`, después `SetDTE`. Son firmas hermanas de los elementos
referenciados por ID; no se agrega automáticamente `enveloped-signature`. Los IDs serán
únicos y se verificará que cada referencia apunte al elemento esperado. Se controlarán
namespaces y espacios desde la construcción y se validará el resultado contra XSD.
**Los bytes firmados son inmutables:** ni Python ni la cola los embellecen o reserializan.
[Manual de certificación y ejemplo de firmas](https://www.sii.cl/factura_electronica/factura_mercado/manual_certificacion.pdf).

El **TED** contiene `DD` (emisor, tipo, folio, fecha, receptor, total, primer ítem, CAF
público y fecha/hora del timbre) y `FRMT`. Se firma `DD` completo, incluidas sus etiquetas,
con la llave privada del CAF: SHA1 con RSA y relleno PKCS#1 v1.5. Su preparación usa
ISO-8859-1, escapes XML, sin espacios entre etiquetas ni referencias de namespaces,
conservando los contenidos terminales. No es C14N de XMLDSig. `FRMA` es la firma del SII
sobre el CAF; `FRMT` es la del timbre. **`RSASK` nunca entra al XML enviado o publicado.**
Se probará el tratamiento de caracteres no representables antes de habilitar emisión.
[Instructivo de emisión, anexo 2](https://www.sii.cl/servicios_online/docs/instructivo_emision.pdf).

La API REST usa servicios separados de autenticación, envío y consulta, TLS 1.2 o
superior y token de boletas. **Endpoints exactos por ambiente, semilla/token,
encabezados, multipart, parámetros y códigos de respuesta: sin verificar.** La fase 0
no pudo acceder a la documentación interactiva; las direcciones recordadas no son un
contrato aprobado. Se cerrará ese contrato antes de escribir el adaptador.
[Instructivo de boletas](https://www.sii.cl/factura_electronica/factura_mercado/Instructivo_Emision_Boleta_Elect.pdf),
[API oficial](https://www4c.sii.cl/bolcoreinternetui/api/).

Para la nota se contrastarán los contratos tradicionales, incluido el upload
`/cgi_dte/UPL/DTEUpload`. El manual de autenticación describe la semilla firmada con
XMLDSig enveloped y referencia vacía; ese perfil no se traslada por analogía a los DTE
ni al contrato REST. URLs operativas y respuestas vigentes del circuito 61: **sin verificar**.
[Autenticación](https://www.sii.cl/factura_electronica/factura_mercado/autenticacion.pdf),
[Envío automático DTE](https://www.sii.cl/factura_electronica/factura_mercado/envio.pdf).

## 4. Venta, folio y documento duradero

**El número de venta no es el folio del SII.** La identidad fiscal es única por
**ambiente + RUT emisor + tipo DTE + folio**, protegida por una restricción en SQLite.
Certificación y producción tendrán configuraciones, CAF, contadores y colas separados.

El flujo será: congelar venta y regla A/B → reservar folio → construir, timbrar y firmar
→ guardar XML y cola → entregar representación → enviar → consultar resultado.
La reserva será atómica y estará ligada a una operación idempotente. La firma ocurre
fuera de la transacción larga; al volver, una transacción guarda documento y trabajo
pendiente juntos. No se imprime ni se informa emisión terminada antes de ese guardado.

Un corte entre reserva y firma deja una operación recuperable, no un folio libre. Si
ya se cobró, se recupera la misma venta: no se vuelve a cobrar ni se crea otra venta.
Una reimpresión usa el documento guardado y nunca consume folio.

| Registro propuesto | Qué conserva |
|---|---|
| `ConfiguracionFiscal` | Contribuyente, ambiente, resolución, firmante, opción A/B y vigencia con constancia. |
| `RangoFolio` / `ReservaFolio` | CAF, rango exclusivo por caja, siguiente folio, operación, reservas y consumos. |
| `DocumentoFiscal` | Venta, identidad fiscal, detalle e impuestos congelados, opción aplicada, XML exacto, hash, CAF, certificado, estado y referencias a notas. |
| `EnvioFiscal` | Adaptador, sobre exacto, documentos incluidos, track ID y respuesta del SII. |
| `IntentoEnvio` | Inicio, término, resultado técnico, error y próximo intento. |
| `EventoFiscal` | Cambios de estado, motivos y acciones de recuperación. |
| `PublicacionBoleta` | Cola independiente para publicar la representación y actualizar su estado. |

La regla actual de [CONTRATO.md](CONTRATO.md) calcula neto e IVA al informar. Para el
documento fiscal se **congelarán al emitir** base, tasa, IVA, exento si corresponde,
total, descuentos y versión del cálculo. Cambiar una tasa o una función no cambiará
boletas antiguas. Pesos enteros y aritmética exacta; redondeos, prorrateos y ventas por
peso deberán cuadrar con los casos de certificación. La regla precisa por caso está
**sin verificar**. Propina y total cobrado se distinguen del monto tributario.

Al importar CAF se comprobarán firma del SII, ambiente de uso, emisor, tipo, rango y
correspondencia de llaves. Se rechazarán rangos superpuestos. Si hay varias cajas
autónomas, cada una tendrá **rangos exclusivos**: compartir un CAF con contadores
independientes provoca duplicados. Se alertará por consumo y días de autonomía, por
ejemplo a siete días, tres días y reserva crítica; separado para tipos 39 y 61.

**Restaurar un respaldo no retrocede el contador.** Se reconciliarán reservas, XML y
envíos posteriores, incluidos los emitidos sin internet. Consultar al SII no alcanza
para encontrar documentos que todavía no se enviaron. Si falta evidencia, se inmoviliza
el rango incierto antes de volver a emitir; nunca se toma el contador viejo como válido.

## 5. Sin internet, envío y estados

**La boleta se genera, timbra y firma al vender. Lo que espera es el envío.** Si faltan
folios o no se puede firmar, no se entregará un comprobante interno como boleta.

| Estado visible | Significado |
|---|---|
| Pendiente | XML firmado y guardado; falta confirmar recepción. |
| Enviada | Recepción confirmada con track ID; falta resultado individual. |
| Aceptada | Resultado individual satisfactorio. |
| Con reparo | Resultado con observaciones que requieren revisión. |
| Rechazada | Rechazo explícito; se conservan código, explicación y respuesta. |

Estados internos: `preparando` para reserva/construcción, `enviando` mientras hay un
intento y `resultado_desconocido` cuando no sabemos si el SII recibió. Un timeout después
del upload no equivale a rechazo ni permite dar el documento por no enviado. Tampoco
la recepción del sobre demuestra aceptación de todas sus boletas.

El envío será inmediato, con plazo de **una hora** según la Res. 74, F.6. La excepción
por falta de cobertura de datos no se extenderá a errores de autenticación o XML. Se
registrarán caída y recuperación, y se enviará al recuperar conexión, sin reiniciar
el plazo con cada intento. [Resolución 74, F.6](https://www.sii.cl/normativa_legislacion/resoluciones/2020/reso74.pdf).

La cola priorizará los más antiguos. Reintentos iniciales a 5, 15, 30 y 60 segundos,
luego cada pocos minutos, con alertas antes de la hora y al vencer. Un rechazo explícito
se deriva a revisión; no entra en un ciclo de reenvío ciego. Tras resultado desconocido
se consulta y reconcilia; si corresponde reenviar, se conserva la identidad fiscal.
El rechazo del sobre y el del documento tendrán tratamientos distintos.

**Nunca se emite otra boleta para esconder un rechazo.** La resolución queda registrada
con su causa y el procedimiento aplicable, sin borrar el XML original. Una devolución
que requiera nota 61 crea otro documento vinculado, con CAF, envío y seguimiento propios;
la boleta original conserva su XML y resultado SII.

El cajero verá folio, «Boleta emitida, pendiente de envío» y reimpresión. El dueño verá
antigüedad de la cola, reparos, rechazos, folios y vencimientos, con acciones concretas.
El despachador seguirá funcionando al cerrar la ventana si hay pendientes, y recuperará
la cola al arrancar Windows. Ese arranque debe ejecutarse bajo el mismo usuario que
protege los secretos; su compatibilidad está **sin verificar**. Un equipo apagado no
puede enviar: se avisará de pendientes antes del cierre de la jornada.

## 6. Certificado, secretos y recuperación

Los secretos vivirán **fuera del árbol que actualiza la caja**, por ejemplo en
`%LOCALAPPDATA%\CajaClara\Fiscal`, con permisos para el usuario que ejecuta el POS.
PFX, contraseña y CAF originales se protegerán con **DPAPI `CurrentUser`**. SQLite
guardará identificadores y metadatos, no llaves privadas ni contraseñas en texto claro.

Al importar el PFX se verificarán llave RSA, vigencia y correspondencia del firmante.
La llave del certificado no volverá a Python. El uso de almacenamiento efímero de
claves en la versión instalada de .NET está **sin verificar**. Se alertará antes del
vencimiento del certificado y se comprobará su vigencia al firmar.

DPAPI depende del perfil y credenciales de Windows. No protege de un proceso malicioso
ejecutado por ese mismo usuario; `LocalMachine` tampoco es un reemplazo apropiado.
[ProtectedData de Microsoft](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.protecteddata?view=netframework-4.8).

Habrá dos respaldos complementarios:

- **Operacional:** SQLite mediante `Connection.backup`, XML exactos, sobres, respuestas,
  eventos y registro de folios reservados y usados.
- **Portátil de secretos:** PFX y CAF originales cifrados, recuperables con una clave
  custodiada por el dueño e independiente de DPAPI. Se preparará y probará al importar.
  Formato, cifrado autenticado y derivación de clave compatibles con Windows PowerShell
  5.1 y su .NET Framework: **sin verificar**; deben cerrarse antes de implementar esa exportación.

En un equipo nuevo se restauran datos, se recuperan los originales con la clave del
dueño, se vuelven a proteger con DPAPI y se reconcilian folios antes de habilitar emisión.
**Copiar archivos DPAPI no es un plan de recuperación.** La prueba debe hacerse bajo
otro perfil o equipo, no solo descifrando en el computador que creó el respaldo.

## 7. Voucher: opción del contribuyente, no del cajero

La configuración guardará opción **A/B**, fecha de vigencia y constancia de lo declarado
ante el SII, sin períodos superpuestos. Cada venta guardará la opción aplicada. Cambiar
la configuración no alterará ventas anteriores ni será una elección por transacción.

Ejemplo ficticio por una venta de $10.000, sin propina:

| Pago | A: voucher sustituye boleta | B: siempre se emite boleta |
|---|---|---|
| Efectivo o transferencia | Boleta por $10.000. | Boleta por $10.000. |
| Tarjeta con voucher válido | Voucher por $10.000; sin otra boleta. | Boleta por $10.000 y voucher de pago. |
| Mixto: $4.000 efectivo y $6.000 tarjeta | Boleta por $4.000 y voucher por $6.000. | Boleta por $10.000 y voucher por $6.000. |

Las transferencias bancarias no se consideran voucher sustituto bajo esta regla.
[Resolución 176 de 2020, resolutivo 2](https://www.sii.cl/normativa_legislacion/resoluciones/2020/reso176.pdf),
[Modelos de emisión del SII](https://www.sii.cl/destacados/boleta_electronica_voucher/).

En A, la venta puede respaldarse con varios documentos; en B, la boleta cubre toda la
venta. **El detalle tributario de la venta mixta en A está sin verificar y se llevará
como caso específico a certificación.** El pago con tarjeta no es un descuento: no se
inventará una línea «descuento tarjeta». La devolución de un voucher también debe
contemplar el procedimiento del operador; su integración está **sin verificar**.

La investigación recogió el anuncio de cambios de modelo mensuales desde el
30-09-2026, efectivos al mes siguiente. Su aplicación al habilitar cada contribuyente
está **sin verificar**; no se supondrá que un cambio local modifica la declaración.
[Operación IVA](https://www.sii.cl/destacados/operacion_iva/).

## 8. Ticket y consulta pública

**No se imprime PDF417 en la boleta 39.** La Res. Ex. SII 207 de 2025 hizo opcional su
impresión desde el **01-01-2026**; el **TED sigue obligatorio dentro del XML**. El encoder
PDF417 queda como mejora opcional. Esta eliminación no se extenderá a la nota 61:
su obligación de timbre impreso está **sin verificar** y se resolverá antes de cerrar
su representación. [Resolución 207 de 2025](https://www.sii.cl/normativa_legislacion/resoluciones/2025/reso207.pdf).

La representación llevará identificación del emisor, tipo, folio, fecha, detalle,
descuentos, IVA, total y referencias cuando correspondan, más la dirección de consulta.
El texto «NO ES BOLETA» solo se retira cuando ese documento sea una boleta emitida de
verdad. La venta presencial debe entregar o poner a disposición la representación
impresa o virtual; tener una web que el comprador no puede localizar no resuelve la
entrega. [Resolución 53 de 2025](https://www.sii.cl/normativa_legislacion/resoluciones/2025/reso53.pdf).

La consulta será un **servicio aparte, en el mismo servidor que tendrá el canal de
actualizaciones propio del producto**. Compartirá infraestructura, pero tendrá servicio,
almacenamiento y credenciales separados. No usará el repositorio público para guardar
documentos. Seguirá disponible cuando la caja esté apagada.

La caja publicará mediante **HTTPS saliente, sin abrir puertos del local**, con una
credencial por instalación y una cola independiente del envío al SII. Publicar en la
web no equivale a enviar al SII. Se elegirá una representación estructurada con los
datos necesarios, evitando enviar el XML completo al portal en la primera versión.

| Sale del local hacia la consulta | No sale hacia la consulta |
|---|---|
| Identificación fiscal del emisor, tipo, folio, fecha, detalle, descuentos, impuestos, total, referencias y datos del receptor que exija la representación. Identificador impredecible y actualizaciones del estado SII. | PFX, contraseñas, llaves del CAF (`RSASK`), tokens SII, base completa, usuarios, PIN, turnos, costos y márgenes internos. |

El XML firmado sí se envía al SII por su adaptador. Si más adelante el portal ofrece
descargarlo, esa transferencia incluirá sus datos de receptor y certificado público;
deberá incorporarse expresamente al contrato de publicación y al aviso del producto.

La consulta será sin cuenta, mediante enlace impredecible impreso o datos del documento,
con protección contra enumeración, sin listados públicos de ventas y con versión
imprimible. Publicará «pendiente de validación» hasta conocer el resultado. Sin internet
se entrega localmente y se publica al recuperar conexión; no se promete consulta
inmediata de una venta que aún no ha salido del equipo.

El formato revisado contempla consulta por **tres meses** y la guía exige un sitio
operativo indicado en las representaciones antes de autorizar. Se propone conservar
localmente XML y evidencia por seis años; el plazo legal completo aplicable y la
política de eliminación están **sin verificar**. No se borrará por confundir el plazo
web con la conservación fiscal.
[Formato de boletas, consulta](https://www.sii.cl/factura_electronica/factura_mercado/formato_boleta_electronica.pdf),
[Guía de certificación](https://www.sii.cl/factura_electronica/guia_emitir_boleta_servicio.htm).

## 9. Fases y pruebas de salida

Estimación para una persona, en días hábiles efectivos, con revisión y pruebas. Es una
estimación de diseño, no una fecha comprometida.

| Fase | Días | Resultado y cómo se comprueba |
|---|---:|---|
| 1. Cerrar contratos técnicos | 2–3 | Fijar XSD, API y perfil del exe antiguo. Inventario y prueba de actualización sin secretos reales. |
| 2. XML, TED, firma y protección local | 6–9 | Boleta y nota, XSD y recuperación. PFX/CAF sintéticos; verificador de firmas independiente. |
| 3. Folios, persistencia y cola | 5–7 | Concurrencia, idempotencia, cortes de luz, restauración y simulador de respuestas SII. |
| 4. Ventas y anulaciones | 4–6 | Cálculo congelado, descuentos, peso, pagos A/B, notas y pantallas de incidencias. |
| 5. Tickets y consulta pública | 4–6 | Impresión real, publicación, consulta y privacidad. Sitio accesible antes de certificar. |
| 6. Integración real de certificación | 5–8 | Certificado autorizado, CAF SII del ambiente para 39/61, set y aceptación individual. |
| 7. Correcciones, muestras y piloto | 4–6 | Evidencias, recuperación completa e impresoras; piloto productivo solo tras autorización. |
| 8. PDF417 opcional, si se construye encoder propio | +4–7 | Raster, lectura independiente y medidas sobre papel; no bloquea la boleta 39. |

**Base: 30–45 días de trabajo**, más espera administrativa; PDF417 propio sumaría 4–7.
Los 10–15 días hábiles de revisión del SII no están incluidos como trabajo efectivo.

Sin certificado real se pueden probar XML, XSD, firmas, DPAPI, cálculos, tickets, portal,
colas y recuperación con datos sintéticos. El CAF de prueba se verificará contra una
autoridad ficticia limitada al entorno de pruebas: **no autoriza folios ni pasará la
firma del SII**. El código productivo no aceptará esa autoridad.

Las pruebas cubrirán tildes, ñ, `&`, comillas, espacios y namespaces; firma antes y después
de envolver; bytes intactos al guardar/reintentar; doble clic y dos cajas; caída entre
reserva, firma, guardado, upload y respuesta; respaldo antiguo y equipo nuevo. Verificar
la firma solo con el mismo código que la produjo no alcanza: en desarrollo se usará
otra implementación. Se probará el **exe más antiguo más solo la actualización de
código**, sin instalar dependencias para que pase la prueba.

La certificación real requiere contribuyente habilitado, firmante autorizado, PFX real,
CAF del SII de ese ambiente, sitio público y muestras. Allí se comprobarán el contrato
HTTP, la aceptación del XML, los casos mixtos A, las notas y sus representaciones.
Certificar boletas no demuestra por sí solo la habilitación del tipo 61.

## 10. Pendientes antes de programar

Todos estos puntos están **sin verificar**. La fase 1 debe cerrar los contratos y dejar
los casos tributarios preparados para su comprobación en certificación.

| Pendiente | Evidencia necesaria |
|---|---|
| REST vigente y adaptador DTE general | Endpoints por ambiente, autenticación, multipart, consultas, respuestas y recuperación de envíos inciertos. No copiar rutas de memoria. |
| XSD vigentes | Archivos y dependencias descargados del [catálogo oficial](https://www.sii.cl/servicios_online/1039-formato_xml-1184.html), con versión, huellas y casos válidos. |
| Exe más antiguo instalado | Módulos disponibles, Windows PowerShell 5.1, versión de .NET, RSA/PFX, DPAPI, TLS y latencia, probados con actualización de código solamente. |
| `RutProvSW` mientras no haya RUT propio | Criterio confirmado con el SII para identificar al proveedor y llenar `RznSocProvSW`; referencia: [formato que incorpora esos campos](https://www.sii.cl/factura_electronica/factura_mercado/formato_boletas_elec_202306.pdf). |
| Habilitación tipo 61 | Trámite y autorización del contribuyente, CAF 61, aceptación por `EnvioDTE` y obligación de timbre impreso. |
| Detalle mixto A y correcciones | Casos de prueba acordados para el set; detalle, reparto tributario, redondeos y devoluciones de voucher aceptados en certificación. |
| Respaldo portátil y conservación | Formato cifrado recuperable con clave del dueño, compatibilidad y restauración en otro perfil; plazos de conservación aplicables. |

La implementación actualizará [CONTRATO.md](CONTRATO.md) junto con el código cuando
estas tablas y reglas existan. Hasta entonces, este es el diseño y no una declaración
de que la caja ya emite boletas.
