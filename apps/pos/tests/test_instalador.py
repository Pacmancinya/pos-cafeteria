"""El instalador de Windows (despliegue/instalador/caja-clara.iss) no puede llevarse las
ventas de un local ni quedar desfasado de la version.

No necesitan Inno Setup: leen el script como texto. Lo que de verdad se instala se prueba
a mano (ver docs/INSTALACION.md).
"""
from __future__ import annotations

import os
import re

from core.config import APP_VERSION
from despliegue import construir_instalador as ci

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
RUTA_ISS = os.path.join(RAIZ, "despliegue", "instalador", "caja-clara.iss")

# Los datos del local: ninguna instruccion del instalador puede borrarlos ni pisarlos.
DATOS = ["pos.db", "pos.db-wal", "pos.db-shm", "respaldos", "registros", ".secreto",
         "datos-ventana", ".acceso-directo", ".env", "_version_anterior"]


def _iss() -> str:
    with open(RUTA_ISS, encoding="utf-8-sig") as f:
        return f.read()


def _secciones(texto: str) -> dict[str, str]:
    partes = re.split(r"^\[(\w+)\]\s*$", texto, flags=re.M)
    return {partes[i].lower(): partes[i + 1] for i in range(1, len(partes), 2)}


def _sin_comentarios(texto: str) -> str:
    return "\n".join(l for l in texto.splitlines() if not l.lstrip().startswith(";"))


def test_se_instala_por_usuario_sin_administrador():
    setup = _secciones(_iss())["setup"]
    assert re.search(r"^PrivilegesRequired=lowest\s*$", setup, re.M)
    # El actualizador escribe dentro de la carpeta: tiene que ser del usuario.
    assert "{autopf}" in setup or "{localappdata}" in setup


def test_avisa_si_la_caja_esta_abierta_con_el_mutex_de_verdad():
    kofe = open(os.path.join(RAIZ, "Kofe.py"), encoding="utf-8").read()
    mutex = re.search(r'^CERROJO\s*=\s*"([^"]+)"', kofe, re.M).group(1)
    assert re.search(rf"^AppMutex={re.escape(mutex)}\s*$", _secciones(_iss())["setup"], re.M)


def test_el_appid_es_fijo_y_no_cambia():
    # Si este valor cambia, una reinstalacion deja de contar como actualizacion.
    assert "AppId={{A6409110-0F01-4DF9-8EA1-BE63F8ACDCE9}" in _iss()


def test_la_version_no_esta_escrita_a_mano():
    texto = _sin_comentarios(_iss())
    assert "#ifndef VersionApp" in texto
    assert re.search(r"^AppVersion=\{#VersionApp\}\s*$", texto, re.M)
    assert "OutputBaseFilename=CajaClara-Instalar-v{#VersionApp}" in texto
    assert APP_VERSION not in texto
    assert not re.search(r"^AppVersion=\d", texto, re.M)


def test_el_script_lleva_bom_para_las_tildes():
    with open(RUTA_ISS, "rb") as f:
        assert f.read(3) == b"\xef\xbb\xbf"


def test_no_hay_instrucciones_que_borren_los_datos_del_local():
    texto = _iss()
    secciones = _secciones(texto)
    # Sin secciones de limpieza: el desinstalador solo borra lo que el mismo instalo.
    assert "uninstalldelete" not in secciones
    assert "installdelete" not in secciones
    codigo = _sin_comentarios(secciones.get("code", "")).lower()
    for peligro in ("deletefile", "deltree", "removedir", "renamefile"):
        assert peligro not in codigo
    # Los datos solo pueden aparecer en las exclusiones de [Files] (para que NO viajen).
    sin_comentarios = _sin_comentarios(texto)
    for nombre in DATOS:
        for linea in sin_comentarios.splitlines():
            if nombre in linea:
                assert "Excludes:" in linea, f"{nombre} aparece fuera de Excludes: {linea}"


def test_los_datos_del_local_no_viajan_dentro_del_instalador():
    archivos = _secciones(_iss())["files"].replace("\\\n", " ")
    excludes = re.search(r'Excludes:\s*"([^"]+)"', archivos).group(1)
    for nombre in DATOS:
        assert nombre in excludes
    assert "ignoreversion" in archivos


def test_los_accesos_directos_y_el_inicio_opcional():
    secciones = _secciones(_iss())
    assert re.search(r'^Name: "inicio".*Flags: unchecked', secciones["tasks"], re.M)
    iconos = secciones["icons"].replace("\\\n", " ")
    assert "{autodesktop}" in iconos and "{autoprograms}" in iconos
    inicio = [l for l in iconos.splitlines() if "{userstartup}" in l]
    assert len(inicio) == 1 and "Tasks: inicio" in inicio[0]
    assert "caja-clara.ico" in iconos
    assert os.path.isfile(os.path.join(RAIZ, "despliegue", "icono", "caja-clara.ico"))


def test_ordenes_de_iscc_pasan_la_version_y_la_carpeta():
    cmd = ci.ordenes("ISCC.exe", version="9.9", origen="X:/origen", salida="X:/salida")
    assert "/DVersionApp=9.9" in cmd
    assert "/DOrigen=X:/origen" in cmd and "/DSalida=X:/salida" in cmd
    assert cmd[-1] == ci.SCRIPT and os.path.isfile(ci.SCRIPT)


def test_sin_la_carpeta_construida_falla_con_un_mensaje_claro(monkeypatch, tmp_path):
    monkeypatch.setattr(ci, "ORIGEN", str(tmp_path))
    try:
        ci.construir()
    except SystemExit as e:
        assert "construir_exe" in str(e)
    else:
        raise AssertionError("tenia que avisar que falta construir la aplicacion")


def test_sin_inno_setup_falla_con_un_mensaje_claro(monkeypatch, tmp_path):
    (tmp_path / "CajaClara.exe").write_bytes(b"")
    monkeypatch.setattr(ci, "ORIGEN", str(tmp_path))
    monkeypatch.setattr(ci, "encontrar_iscc", lambda: None)
    try:
        ci.construir()
    except SystemExit as e:
        assert "Inno Setup" in str(e) and "winget" in str(e)
    else:
        raise AssertionError("tenia que avisar que falta Inno Setup")
