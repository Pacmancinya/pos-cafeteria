"""Lo que se puede probar sin una balanza al otro lado: que no haga nada raro sin red.

El resto de la herramienta son conexiones de verdad y se prueba en el local, con la balanza
encendida. Acá solo se protege que las equivocaciones de quien la corre —olvidar la IP,
escribir un nombre en vez de un número— terminen en una frase útil y no en un error de
Python.
"""

from __future__ import annotations

from tools.balanza.explorar import PUERTOS, explorar, main


def test_sin_ip_explica_donde_buscarla(capsys):
    assert main([]) == 1
    salida = capsys.readouterr().out
    assert "Falta la IP" in salida
    assert "router" in salida          # le dice dónde mirar, no solo que falta


def test_algo_que_no_es_una_ip_no_revienta(capsys):
    assert explorar("la balanza") == 1
    assert "no parece una dirección IP" in capsys.readouterr().out


def test_no_barre_la_red_entera():
    """Es una lista corta de puertos conocidos, no un barrido.

    Si alguien la convierte en un escáner de rangos, esto lo caza: la herramienta existe
    para golpear una puerta conocida de un equipo propio, no para recorrer una red.
    """
    assert len(PUERTOS) <= 15
    assert all(isinstance(p, int) and 0 < p < 65536 for p in PUERTOS)
