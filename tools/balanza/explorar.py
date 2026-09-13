"""Averiguar qué habla la balanza de un local, antes de programar nada contra ella.

    python -m tools.balanza.explorar 192.168.1.50

La balanza de etiquetas del primer local (una DIGI SM-300) está en la WiFi y el punto de
venta que usan hoy le pide el detalle de cada ticket. Para que Kofe haga lo mismo hay que
saber por dónde: unas sirven los datos por FTP, otras por una página web propia, otras por
un puerto propio con un protocolo binario. La diferencia entre esos casos es la diferencia
entre un par de días de trabajo y varias semanas, así que conviene mirar antes de decidir.

Esto **no fuerza nada**: abre una conexión a una lista corta de puertos conocidos, saluda
como lo haría cualquier cliente y cuenta qué contestó. Es el equivalente a golpear la
puerta. Se corre sobre la balanza del propio local, desde la misma red.
"""

from __future__ import annotations

import socket
import sys
import urllib.error
import urllib.request

# Los puertos donde una balanza o un periférico de local suelen ofrecer algo. La lista es
# corta a propósito: no es un barrido, son los sitios donde de verdad hay algo que mirar.
PUERTOS = {
    21: "FTP (archivos: lo más cómodo si deja bajar las ventas)",
    22: "SSH",
    23: "Telnet (consola de configuración)",
    80: "web (página de configuración de la balanza)",
    443: "web segura",
    515: "impresión LPR",
    631: "impresión IPP",
    2000: "puerto propio (DIGI y otras marcas lo usan)",
    3001: "puerto propio",
    8000: "web alternativa",
    8080: "web alternativa",
    9100: "impresión directa (JetDirect)",
}

ESPERA = 1.5


def puerto_abierto(ip: str, puerto: int, espera: float = ESPERA) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(espera)
        return s.connect_ex((ip, puerto)) == 0


def saludo(ip: str, puerto: int, espera: float = ESPERA) -> str:
    """Lo primero que dice el servicio al conectarse. FTP y Telnet se presentan solos."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(espera)
            s.connect((ip, puerto))
            return s.recv(200).decode("latin-1", "replace").strip()
    except OSError:
        return ""


def pagina(ip: str, puerto: int, espera: float = ESPERA) -> str:
    esquema = "https" if puerto == 443 else "http"
    url = f"{esquema}://{ip}:{puerto}/"
    try:
        with urllib.request.urlopen(url, timeout=espera) as r:
            cuerpo = r.read(400).decode("latin-1", "replace")
            titulo = ""
            bajo = cuerpo.lower()
            if "<title>" in bajo:
                i = bajo.index("<title>") + 7
                titulo = cuerpo[i:bajo.index("</title>", i)].strip()
            return f"HTTP {r.status} · {titulo or cuerpo[:80].strip()}"
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code} (contesta, pide credenciales o no existe esa ruta)"
    except Exception as e:  # noqa: BLE001 - acá cualquier fallo es "no contesta como web"
        return f"no contestó como web ({e.__class__.__name__})"


def explorar(ip: str) -> int:
    print(f"Mirando la balanza en {ip}\n")
    try:
        socket.inet_aton(ip)
    except OSError:
        print(f"'{ip}' no parece una dirección IP. Busca la de la balanza en su menú de red,"
              " o en la lista de equipos del router.")
        return 1

    if not any(puerto_abierto(ip, p, 0.6) for p in (80, 21, 23, 9100, 2000)):
        print("No contesta en ninguno de los puertos habituales. Revisa que:")
        print("  - estés en la MISMA red WiFi que la balanza (no en la de invitados)")
        print("  - la balanza esté encendida y con su IP correcta")
        print("  - la IP sea la de la balanza y no la de otro equipo")
        return 1

    encontrados = []
    for puerto, que_es in sorted(PUERTOS.items()):
        if not puerto_abierto(ip, puerto):
            continue
        encontrados.append(puerto)
        detalle = ""
        if puerto in (80, 443, 8000, 8080):
            detalle = pagina(ip, puerto)
        else:
            detalle = saludo(ip, puerto) or "(abierto, no se presenta solo)"
        print(f"  {puerto:>5}  {que_es}")
        print(f"         -> {detalle}\n")

    print("-" * 62)
    if 21 in encontrados:
        print("Hay FTP. Es el mejor caso: probablemente deja bajar las ventas como archivo,")
        print("y conectar Kofe sería leer ese archivo. Entra con un cliente FTP y mira qué")
        print("carpetas tiene.")
    elif any(p in encontrados for p in (80, 443, 8000, 8080)):
        print("Tiene página web propia. Ábrela en el navegador: casi siempre trae la")
        print("configuración y, con suerte, una forma de exportar las ventas.")
    else:
        print("Solo puertos propios. Ahí el detalle del ticket viaja en un protocolo de la")
        print("marca y hay que averiguarlo con el manual o con el proveedor de la balanza.")
    print("\nMándame esta salida completa y te digo qué cuesta conectar Kofe.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = (argv if argv is not None else sys.argv[1:])
    if not args:
        print(__doc__.strip().splitlines()[2].strip())
        print("\nFalta la IP de la balanza. Está en su menú de red, o en la lista de equipos")
        print("conectados del router (suele aparecer como DIGI o con su número de serie).")
        return 1
    return explorar(args[0])


if __name__ == "__main__":
    sys.exit(main())
