#!/bin/sh
# Las pantallas del local viven en apps/pos/static/pantallas.html, que es el
# archivo que sirve la caja en /pantallas. Este script saca la cabecera HTML y
# deja el fragmento que se publica como Artifact para mirarlo desde el celular.
#
#   sh despliegue/artifact_pantallas.sh
sed '1,9d' apps/pos/static/pantallas.html | head -n -2 > despliegue/pantallas-artifact.html
echo "despliegue/pantallas-artifact.html actualizado"
