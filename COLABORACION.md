# Trabajar juntos en Caja Clara

Este repositorio privado contiene el proyecto completo para desarrollar: código,
pruebas, documentación, recursos gráficos y scripts para construir el instalador.
Parte de la versión 2.31, commit `7b550d2` de `Pacmancinya/pos-cafeteria`,
como una copia nueva sin el historial anterior.

## Desarrollo separado de las cajas reales

- `Pacmancinya/caja-clara`: colaboración privada. Subir código aquí no actualiza locales.
- `Pacmancinya/pos-cafeteria`: distribución actual. Se mantiene sin cambios.
- El código conserva las URLs originales de actualización por compatibilidad.
  No usar «Buscar actualizaciones» en la copia de desarrollo: podría reemplazar el
  trabajo local por la versión publicada. Nunca desarrollar sobre una instalación real.
- Los archivos de versión y firma son los de la versión de origen. No sirven para
  firmar los cambios nuevos. El traslado de mejoras a distribución y su publicación
  se hace por separado, con autorización de Ruperto y primero al canal piloto.

## Empezar en Windows

```powershell
git clone https://github.com/Pacmancinya/caja-clara.git
cd caja-clara
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m tools.demo.seed
.\.venv\Scripts\python.exe -m uvicorn apps.pos.main:app --host 127.0.0.1 --port 8090
```

Abrir `http://127.0.0.1:8090`. Usar un computador o carpeta de pruebas, nunca datos
de un local. Si ya hay una caja en ese puerto, no detenerla: usar otro, por ejemplo 8091.
La base de demostración se crea localmente y no se sube.

## Proponer cambios

1. Crear una rama por mejora o arreglo.
2. Modificar cualquier parte del proyecto que requiera esa tarea.
3. Ejecutar `.venv/Scripts/python -m pytest apps core tools -q`.
   Instalar Node para que también se ejecuten las pruebas JavaScript.
4. Revisar `git status` y el diff; añadir archivos por rutas exactas.
5. Enviar un pull request hacia main explicando qué cambia y cómo se probó.

Los cambios visuales también se comprueban en pantallas chicas con
`tools/pantallas/auditar.py`. Leer `AGENTS.md`, `README.md` y `docs/CONTRATO.md`.

## Lo que no se comparte

Nunca subir bases de datos, ventas, respaldos, registros, `.env`, `.secreto`,
cookies, credenciales, datos de clientes ni la llave privada de firma.
No se incluyen ejecutables ni entornos instalados: se construyen desde el código.
El carácter privado del repositorio no cambia estas reglas.

Ruperto invita a cada colaborador por su usuario de GitHub desde
Settings → Collaborators. Compartir el enlace no da acceso por sí solo.
