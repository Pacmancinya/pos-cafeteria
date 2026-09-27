"""El puente de pantalla completa sin abrir una ventana ni importar .NET."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import ast
from pathlib import Path
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


def rectangulo(ancho, alto, x=0, y=0):
    return SimpleNamespace(Width=ancho, Height=alto, X=x, Y=y)


def punto(x, y):
    return SimpleNamespace(X=x, Y=y)


@pytest.fixture
def winforms_falso(monkeypatch):
    class Form:
        def __init__(self, ancho=1700, alto=1075, escala=1.25, maximizada=False):
            self._scale = escala
            self._size = rectangulo(ancho, alto)
            self._location = punto(0, 0)
            self.RestoreBounds = rectangulo(ancho, alto)
            self.area = rectangulo(1366, 728)
            self.cambios = []
            self.en_interfaz = False
            self.invocaciones = 0
            self.IsHandleCreated = True
            self.Visible = True
            self._minimo = rectangulo(int(1024 * escala), int(680 * escala))
            self._estado = "Maximized" if maximizada else "Normal"
            if maximizada:
                self._size = rectangulo(self.area.Width, self.area.Height)

        def Invoke(self, delegado):
            self.invocaciones += 1
            self.en_interfaz = True
            try:
                delegado()
            finally:
                self.en_interfaz = False

        @property
        def Size(self):
            return self._size

        @Size.setter
        def Size(self, valor):
            assert self.en_interfaz
            assert self._estado == "Normal"
            assert valor.Width >= self._minimo.Width
            assert valor.Height >= self._minimo.Height
            self.cambios.append(("tamano", valor.Width, valor.Height))
            self._size = valor

        @property
        def Location(self):
            return self._location

        @Location.setter
        def Location(self, valor):
            assert self.en_interfaz
            assert self._estado == "Normal"
            self.cambios.append(("ubicacion", valor.X, valor.Y))
            self._location = valor

        @property
        def MinimumSize(self):
            return self._minimo

        @MinimumSize.setter
        def MinimumSize(self, valor):
            assert self.en_interfaz
            self.cambios.append(("minimo", valor.Width, valor.Height))
            self._minimo = valor

        @property
        def WindowState(self):
            return self._estado

        @WindowState.setter
        def WindowState(self, valor):
            assert self.en_interfaz
            self.cambios.append(("estado", valor))
            if valor == "Maximized" and self._estado == "Normal":
                self.RestoreBounds = rectangulo(
                    self.Size.Width, self.Size.Height, self.Location.X, self.Location.Y,
                )
            if valor == "Normal" and self._estado == "Maximized":
                self._size = rectangulo(self.RestoreBounds.Width, self.RestoreBounds.Height)
                self._location = punto(self.RestoreBounds.X, self.RestoreBounds.Y)
            self._estado = valor
            # Windows respeta el mínimo incluso al maximizar.
            if valor == "Maximized":
                self._size = rectangulo(max(self.area.Width, self._minimo.Width),
                                        max(self.area.Height, self._minimo.Height))

    class Func:
        def __class_getitem__(cls, tipo):
            return lambda funcion: funcion

    def desde_control(form):
        assert form.en_interfaz
        def contiene(frame):
            return (form.area.X <= frame.X
                    and form.area.Y <= frame.Y
                    and frame.X + frame.Width <= form.area.X + form.area.Width
                    and frame.Y + frame.Height <= form.area.Y + form.area.Height + 40)

        return SimpleNamespace(WorkingArea=form.area,
                               Bounds=SimpleNamespace(Contains=contiene))

    monkeypatch.setitem(ventana.sys.modules, "System", SimpleNamespace(Func=Func, Type=type))
    monkeypatch.setitem(ventana.sys.modules, "System.Drawing", SimpleNamespace(
        Size=rectangulo, Point=punto,
    ))
    monkeypatch.setitem(ventana.sys.modules, "System.Windows.Forms", SimpleNamespace(
        Form=Form, FormWindowState=SimpleNamespace(Normal="Normal", Maximized="Maximized"),
        Screen=SimpleNamespace(FromControl=desde_control),
    ))
    return Form


@pytest.mark.parametrize("escala", [1, 1.25, 1.5, 2])
def test_ventana_grande_baja_minimo_antes_de_maximizar(winforms_falso, escala):
    form = winforms_falso(int(1360 * escala), int(860 * escala), escala)
    nativa = SimpleNamespace(native=form)
    # frame es el WorkingArea nativo; scale puede ser 1 con DPI al 125%.
    modulo = SimpleNamespace(screens=[SimpleNamespace(frame=form.area, scale=1)])
    ventana._ajustar_a_pantalla(modulo, nativa)
    assert form.invocaciones == 1
    assert form.cambios == [
        ("minimo", min(int(800 * escala), 1366), min(int(500 * escala), 728)),
        ("estado", "Normal"),
        ("tamano", min(int(1360 * escala), 1366), 728),
        ("ubicacion", (1366 - min(int(1360 * escala), 1366)) // 2, 0),
        ("estado", "Maximized"),
    ]
    assert form.Size.Width <= 1366
    assert form.Size.Height <= 728
    assert form.RestoreBounds.Width <= 1366
    assert form.RestoreBounds.Height <= 728


@pytest.mark.parametrize("ancho,alto", [(1000, 625), (1366, 728)])
def test_ventana_que_cabe_no_se_toca(winforms_falso, ancho, alto):
    form = winforms_falso(ancho, alto)
    ventana._ajustar_a_pantalla(SimpleNamespace(screens=[]), SimpleNamespace(native=form))
    assert form.cambios == []
    assert (form.Size.Width, form.Size.Height) == (ancho, alto)


def test_pywebview_viejo_sin_screens_ni_scale_usa_winforms(winforms_falso):
    form = winforms_falso()
    del form._scale
    form.DeviceDpi = 120
    ventana._ajustar_a_pantalla(SimpleNamespace(), SimpleNamespace(native=form))
    assert form.cambios == [
        ("minimo", 1000, 625), ("estado", "Normal"),
        ("tamano", 1366, 728), ("ubicacion", 0, 0), ("estado", "Maximized"),
    ]


def test_minimo_nunca_supera_un_area_de_trabajo_pequena(winforms_falso):
    form = winforms_falso()
    form.area = rectangulo(900, 550)
    ventana._ajustar_a_pantalla(SimpleNamespace(), SimpleNamespace(native=form))
    assert form.cambios[0] == ("minimo", 900, 550)


def test_usa_la_pantalla_actual_y_no_la_de_creacion(winforms_falso):
    form = winforms_falso()
    form.area = rectangulo(1366, 728, x=2560)
    # En la pantalla de creación 1700x1075 cabe: elegirla por error no ajusta nada.
    principal = SimpleNamespace(frame=rectangulo(2560, 1400))
    actual = SimpleNamespace(frame=form.area)
    nativa = SimpleNamespace(native=form, screen=principal)
    modulo = SimpleNamespace(screens=[principal, actual])
    ventana._ajustar_a_pantalla(modulo, nativa)
    assert form.cambios == [
        ("minimo", 1000, 625), ("estado", "Normal"),
        ("tamano", 1366, 728), ("ubicacion", 2560, 0), ("estado", "Maximized"),
    ]


@pytest.mark.parametrize("ancho,alto,w,h,x,y", [
    (1700, 1075, 1366, 728, -1920, 40),
    (1200, 1075, 1200, 728, -1837, 40),
    (1700, 650, 1366, 650, -1920, 79),
])
@pytest.mark.parametrize("maximizada", [False, True])
def test_acota_y_centra_el_tamano_normal_antes_de_maximizar(
    winforms_falso, ancho, alto, w, h, x, y, maximizada,
):
    form = winforms_falso(ancho, alto, maximizada=maximizada)
    form.area = rectangulo(1366, 728, x=-1920, y=40)
    ventana._ajustar_a_pantalla(SimpleNamespace(), SimpleNamespace(native=form))
    assert form.invocaciones == 1
    assert form.cambios == [
        ("minimo", 1000, 625), ("estado", "Normal"),
        ("tamano", w, h), ("ubicacion", x, y), ("estado", "Maximized"),
    ]
    assert form.RestoreBounds == rectangulo(w, h, x, y)
    # Simula restaurar con la barra de título o el exe antiguo instalado.
    form.Invoke(lambda: setattr(form, "WindowState", "Normal"))
    assert (form.Size.Width, form.Size.Height) == (w, h)
    assert form.Location == punto(x, y)


def test_ya_maximizada_con_restorebounds_que_cabe_no_se_toca(winforms_falso):
    form = winforms_falso(1200, 700, maximizada=True)
    # Size puede incluir el borde invisible de la ventana maximizada.
    form._size = rectangulo(1382, 744)
    ventana._ajustar_a_pantalla(SimpleNamespace(), SimpleNamespace(native=form))
    assert form.cambios == []
    assert form.WindowState == "Maximized"
    assert form.RestoreBounds == rectangulo(1200, 700)


def test_screens_que_falla_recurre_a_winforms(winforms_falso, caplog):
    class WebviewViejo:
        @property
        def screens(self):
            raise RuntimeError("No hay screens")

    form = winforms_falso()
    ventana._ajustar_a_pantalla(WebviewViejo(), SimpleNamespace(native=form))
    assert form.WindowState == "Maximized"
    assert "se usará WinForms" in caplog.text


@pytest.mark.parametrize("nativa", [SimpleNamespace(), SimpleNamespace(native=object())])
def test_native_incompatible_solo_registra_aviso(winforms_falso, caplog, nativa):
    ventana._ajustar_a_pantalla(SimpleNamespace(), nativa)
    assert "No se pudo preparar el ajuste" in caplog.text


def test_error_de_invoke_no_interrumpe_el_arranque(winforms_falso, caplog):
    form = winforms_falso()

    def fallar(delegado):
        raise RuntimeError("Formulario cerrado")

    form.Invoke = fallar
    ventana._ajustar_a_pantalla(SimpleNamespace(), SimpleNamespace(native=form))
    assert form.cambios == []
    assert "No se pudo preparar el ajuste" in caplog.text


def test_no_maximiza_si_falla_el_cambio_de_minimo(winforms_falso, caplog):
    class FormConError(winforms_falso):
        @winforms_falso.MinimumSize.setter
        def MinimumSize(self, valor):
            raise RuntimeError("No se pudo bajar el mínimo")

    form = FormConError()
    ventana._ajustar_a_pantalla(SimpleNamespace(), SimpleNamespace(native=form))
    assert form.cambios == []
    assert "No se pudo ajustar la ventana" in caplog.text


def test_espera_shown_aunque_native_ya_exista(monkeypatch, winforms_falso):
    form = winforms_falso()
    nativa = VentanaFalsa()
    nativa.native = form
    listo = False
    nativa.events = SimpleNamespace(shown=SimpleNamespace(is_set=lambda: listo))

    def mostrar():
        nonlocal listo
        assert form.cambios == []
        assert len(nativa.expuestas) == 1
        listo = True

    monkeypatch.setattr(ventana, "time", RelojFalso(mostrar))
    ventana._esperar_ventana(SimpleNamespace(windows=[nativa]))
    assert form.WindowState == "Maximized"


@pytest.mark.parametrize("area,esperado", [
    ((1920, 1040), False), ((1360, 860), False), ((1366, 728), True),
    ((1366 / 1.25, 728 / 1.25), True), ((1300, 1000), True),
])
def test_decision_pura_de_maximizar(area, esperado):
    assert ventana.necesita_maximizar(1360, 860, *area) is esperado


def funcion_lanzador(nombre, contexto):
    # Extraemos sólo la función para no importar el lanzador, que cambia cwd
    # y carga las librerías del exe. El doble no abre ventanas ni importa .NET.
    ruta = Path(__file__).resolve().parents[3] / "Kofe.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    funcion = next(n for n in arbol.body
                   if isinstance(n, ast.FunctionDef) and n.name == nombre)
    exec(compile(ast.Module(body=[funcion], type_ignores=[]), str(ruta), "exec"), contexto)
    return contexto[nombre]


@pytest.fixture
def decision_lanzador():
    contexto = {
        "sys": SimpleNamespace(platform="win32"),
        "ctypes": SimpleNamespace(windll=SimpleNamespace(user32=SimpleNamespace(
            SetProcessDPIAware=lambda: None, GetDpiForSystem=lambda: 120))),
    }
    funcion_lanzador("_abrir_maximizada", contexto)
    return contexto


@pytest.mark.parametrize("ancho,alto,esperado", [
    (1920, 1040, (True, 1360, 832)),
    (2560, 1400, (False, 1360, 860)),
    (1366, 728, (True, 1092, 582)),
    (1600, 1400, (True, 1280, 860)),
    (1700, 1075, (False, 1360, 860)),
])
def test_lanzador_convierte_area_fisica_con_dpi_del_sistema(
    decision_lanzador, ancho, alto, esperado,
):
    # 1920x1040 físicos al 125% dan 1536x832 lógicos: falta altura.
    principal = SimpleNamespace(x=0, y=0, frame=rectangulo(ancho, alto), scale=1)
    secundaria = SimpleNamespace(x=-2560, y=0, frame=rectangulo(2560, 1400))
    decision_lanzador["webview"] = SimpleNamespace(screens=[secundaria, principal])
    assert decision_lanzador["_abrir_maximizada"]() == esperado


def test_lanzador_sin_screens_sigue_abriendo(decision_lanzador):
    decision_lanzador["webview"] = SimpleNamespace()
    assert decision_lanzador["_abrir_maximizada"]() == (False, 1360, 860)


def test_lanzador_screens_que_lanza_error_sigue_abriendo(decision_lanzador):
    class WebviewConError:
        @property
        def screens(self):
            raise RuntimeError("Pantallas no disponibles")

    decision_lanzador["webview"] = WebviewConError()
    assert decision_lanzador["_abrir_maximizada"]() == (False, 1360, 860)


@pytest.mark.parametrize("minimizada,comando", [(True, 9), (False, 5)])
def test_traer_al_frente_solo_restaura_si_esta_minimizada(minimizada, comando):
    llamadas = []

    def encontrar(clase, titulo):
        assert clase is None
        assert titulo == "Caja de prueba"
        return 1234

    def es_iconica(hwnd):
        llamadas.append(("IsIconic", hwnd))
        return minimizada

    user32 = SimpleNamespace(
        FindWindowW=encontrar,
        IsIconic=es_iconica,
        ShowWindow=lambda *args: llamadas.append(("ShowWindow", *args)),
        SetForegroundWindow=lambda hwnd: llamadas.append(("SetForegroundWindow", hwnd)),
    )
    traer = funcion_lanzador("traer_al_frente", {
        "ctypes": SimpleNamespace(windll=SimpleNamespace(user32=user32), c_wchar_p=str),
        "_titulo": lambda: "Caja de prueba",
    })
    traer()
    assert llamadas == [
        ("IsIconic", 1234), ("ShowWindow", 1234, comando), ("SetForegroundWindow", 1234),
    ]


def test_traer_al_frente_sin_ventana_no_llama_a_showwindow():
    traer = funcion_lanzador("traer_al_frente", {
        "ctypes": SimpleNamespace(
            windll=SimpleNamespace(user32=SimpleNamespace(FindWindowW=lambda *args: 0)),
            c_wchar_p=str,
        ),
        "_titulo": lambda: "Caja de prueba",
    })
    traer()


def test_crear_ventana_recibe_el_tamano_acotado_del_lanzador(decision_lanzador):
    ruta = Path(__file__).resolve().parents[3] / "Kofe.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    main = next(n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    # Ejecutamos la preparación y la llamada reales, sin arrancar el servidor.
    inicio = next(i for i, n in enumerate(main.body)
                  if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
                  and isinstance(n.value.func, ast.Name)
                  and n.value.func.id == "_abrir_maximizada")
    creaciones = []
    decision_lanzador.update({
        "NOMBRE_VENTANA_BASE": "Caja", "NOMBRE_LOCAL": "Prueba", "PUERTO": 8090,
        "_titulo": lambda: "Caja Clara",
        "webview": SimpleNamespace(
            screens=[SimpleNamespace(x=0, y=0, frame=rectangulo(1366, 728))],
            create_window=lambda *args, **kwargs: creaciones.append(kwargs),
        ),
    })
    exec(compile(ast.Module(body=main.body[inicio:inicio + 2], type_ignores=[]),
                 str(ruta), "exec"), decision_lanzador)
    assert len(creaciones) == 1
    assert creaciones[0]["maximized"] is True
    assert (creaciones[0]["width"], creaciones[0]["height"]) == (1092, 582)


def test_espera_native_en_version_sin_evento_shown(monkeypatch, winforms_falso):
    form = winforms_falso()
    nativa = VentanaFalsa()
    nativa.native = None
    reloj = RelojFalso(lambda: setattr(nativa, "native", form))
    monkeypatch.setattr(ventana, "time", reloj)
    ventana._esperar_ventana(SimpleNamespace(windows=[nativa]))
    assert reloj.ahora >= ventana._INTERVALO
    assert form.WindowState == "Maximized"


def test_espera_del_formulario_tiene_limite(monkeypatch, caplog):
    nativa = VentanaFalsa()
    nativa.native = None
    reloj = RelojFalso()
    monkeypatch.setattr(ventana, "time", reloj)
    monkeypatch.setattr(ventana, "_ESPERA_VENTANA", 0.2)
    ventana._esperar_ventana(SimpleNamespace(windows=[nativa]))
    assert len(nativa.expuestas) == 1
    assert 0.2 <= reloj.ahora <= 0.25
    assert "no llegó a mostrarse" in caplog.text
