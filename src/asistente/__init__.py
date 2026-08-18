# src/asistente/__init__.py
"""Paquete del asistente.

Aquí solo hay una cosa, y es de arranque: hacer que Python confíe en los
certificados que el sistema operativo ya considera de fiar.

Python no usa el almacén del sistema, sino el paquete `certifi`: una lista
fija de autoridades públicas. En una red doméstica normal da igual, pero en
cualquier red corporativa o escolar con inspección de tráfico (Zscaler,
Netskope, un cortafuegos con SSL inspection...) el proxy reemplaza el
certificado de cada web por uno suyo, firmado por una raíz que el
administrador instaló en el sistema. `curl` y el navegador funcionan; Python
no, y falla con CERTIFICATE_VERIFY_FAILED.

Eso llega al usuario disfrazado: la herramienta del clima devuelve "no se ha
podido consultar" y el asistente se justifica diciendo que no tiene
internet, cuando la red va perfectamente. Peor aún, suele afectar solo a
unos servicios y no a otros —los proxies exentan los dominios grandes—, así
que el asistente parece tener internet a ratos.

`truststore` redirige la verificación al almacén del sistema (llavero en
macOS, almacén de certificados en Windows, ca-certificates en Linux), que es
justo donde está esa raíz. Se inyecta aquí, en el `__init__` del paquete, y
no en `__main__`, porque tiene que valer también para los scripts de
`scripts/`: todos importan algo de `asistente`, y ninguno pasa por
`__main__`. Y se hace antes de que nadie cree un cliente HTTP, porque el
parche actúa sobre los contextos SSL que se creen a partir de ese momento.
"""

try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001
    # Si truststore no está instalado, o el almacén del sistema no se deja
    # leer, se sigue con la verificación de siempre. Eso funciona en una red
    # sin inspección de tráfico, que es el caso normal: mejor un asistente
    # que arranca y falla en una herramienta concreta que uno que no
    # arranca. No se imprime nada porque esto corre en cada import.
    pass
