"""El puente de pantalla completa sin abrir una ventana ni importar .NET."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from tools import ventana


class VentanaFalsa:
    def __init__(self, completa=False):
        self.fullscreen = completa
        self.alternancias = 0
        self.expuestas = []

    def toggle_fullscreen(self):
        self.alternancias += 1

    def expose(self, funcion):
        self.expuestas.append(funcion)


def test_consultar_no_cambia_la_ventana():
    nativa = VentanaFalsa()
    control = ventana._crear_control(nativa)
    assert control() is False
    assert control(None) is False
    assert nativa.alternancias == 0


def test_establecer_es_idempotente_y_se_puede_salir():
    nativa = VentanaFalsa()
    control = ventana._crear_control(nativa)
    assert control(True) is True
    assert control(True) is True
    assert control() is True
    # pywebview tampoco actualiza el atributo fullscreen al alternar.
    assert nativa.fullscreen is False
    assert nativa.alternancias == 1
    assert control(False) is False
    assert control(False) is False
    assert nativa.alternancias == 2


def test_respeta_una_ventana_que_ya_se_abrio_completa():
    nativa = VentanaFalsa(completa=True)
    control = ventana._crear_control(nativa)
    assert control() is True
    assert control(True) is True
    assert nativa.alternancias == 0
    assert control(False) is False
    assert nativa.alternancias == 1


@pytest.mark.parametrize("valor", ["true", "false", 0, 1, [], {}])
def test_el_puente_solo_acepta_booleanos(valor):
    nativa = VentanaFalsa()
    control = ventana._crear_control(nativa)
    with pytest.raises(ValueError, match="booleano"):
        control(valor)
    assert control() is False
    assert nativa.alternancias == 0


def test_un_error_nativo_no_cambia_el_estado(monkeypatch):
    nativa = VentanaFalsa()
    control = ventana._crear_control(nativa)

    def fallar():
        raise RuntimeError("La ventana no está disponible")

    monkeypatch.setattr(nativa, "toggle_fullscreen", fallar)
    with pytest.raises(RuntimeError, match="no está disponible"):
        control(True)
    assert control() is False


def test_peticiones_simultaneas_no_alternan_dos_veces():
    nativa = VentanaFalsa()
    control = ventana._crear_control(nativa)
    with ThreadPoolExecutor(max_workers=8) as hilos:
        estados = list(hilos.map(control, [True] * 24))
    assert estados == [True] * 24
    assert nativa.alternancias == 1


def test_el_servidor_normal_no_arranca_un_hilo(monkeypatch):
    monkeypatch.delitem(ventana.sys.modules, "webview", raising=False)

    def hilo_inesperado(**kwargs):
        pytest.fail("No debe abrirse un hilo sin el lanzador de escritorio")

    monkeypatch.setattr(ventana, "Thread", hilo_inesperado)
    ventana.iniciar()


def test_el_puente_arranca_una_sola_vez_y_en_segundo_plano(monkeypatch):
    modulo = SimpleNamespace(windows=[])
    creados = []

    class HiloFalso:
        def __init__(self, **kwargs):
            self.config = kwargs
            self.arrancado = False
            creados.append(self)

        def start(self):
            self.arrancado = True

    monkeypatch.setitem(ventana.sys.modules, "webview", modulo)
    monkeypatch.setattr(ventana, "Thread", HiloFalso)
    monkeypatch.setattr(ventana, "_iniciado", False)
    ventana.iniciar()
    ventana.iniciar()
    assert len(creados) == 1
    assert creados[0].arrancado
    assert creados[0].config["daemon"] is True
    assert creados[0].config["target"] is ventana._esperar_ventana
    assert creados[0].config["args"] == (modulo,)


class RelojFalso:
    def __init__(self, al_esperar=lambda: None):
        self.ahora = 0.0
        self.al_esperar = al_esperar

    def monotonic(self):
        return self.ahora

    def sleep(self, segundos):
        self.ahora += segundos
        self.al_esperar()


def test_espera_la_ventana_y_expone_solo_el_control(monkeypatch):
    nativa = VentanaFalsa()
    modulo = SimpleNamespace(windows=[])
    reloj = RelojFalso(lambda: modulo.windows.append(nativa))
    monkeypatch.setattr(ventana, "time", reloj)
    ventana._esperar_ventana(modulo)
    assert len(nativa.expuestas) == 1
    control = nativa.expuestas[0]
    assert control.__name__ == "pantalla_completa"
    assert control(True) is True
    # El mismo callable que pywebview vuelve a inyectar tras una recarga
    # consulta el estado actual, sin reconstruir el controlador.
    assert nativa.expuestas[0]() is True
    assert nativa.alternancias == 1


def test_la_espera_termina_si_el_lanzador_no_crea_ventana(monkeypatch):
    reloj = RelojFalso()
    monkeypatch.setattr(ventana, "time", reloj)
    monkeypatch.setattr(ventana, "_ESPERA_VENTANA", 0.2)
    ventana._esperar_ventana(SimpleNamespace(windows=[]))
    assert 0.2 <= reloj.ahora <= 0.25
