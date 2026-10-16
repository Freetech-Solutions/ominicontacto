# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions

# This file is part of OMniLeads

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3, as published by
# the Free Software Foundation.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see http://www.gnu.org/licenses/.
#

"""
Cliente HTTP con protección contra SSRF para las interacciones con Sitios Externos.

- Sólo se permiten los esquemas http y https.
- Las direcciones que no son públicas (privadas, loopback, link-local, CGNAT, reservadas,
  multicast, etc.) se bloquean, salvo que estén habilitadas en la variable de Constance
  SITIO_EXTERNO_ALLOWLIST (hosts y/o CIDRs separados por coma, espacio o salto de línea).
- La validación se hace al momento de abrir la conexión, conectándose a la IP validada,
  para evitar ataques de DNS rebinding.
- No se siguen redirects.
"""

from __future__ import unicode_literals

import ipaddress
import logging
import socket
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import ConnectTimeoutError, NewConnectionError

from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

ESQUEMAS_PERMITIDOS = ('http', 'https')
TIMEOUT_DEFAULT = 10

# NAT64 (RFC 6052): puede traducir a una IPv4 interna
NAT64_PREFIX = ipaddress.ip_network('64:ff9b::/96')


class DestinoNoPermitidoError(Exception):
    """ La URL apunta a un destino no permitido para Sitios Externos """


class AllowList(object):
    """ Hosts y redes privadas habilitadas como destino de Sitios Externos """

    def __init__(self, hosts=(), redes=()):
        self.hosts = frozenset(hosts)
        self.redes = tuple(redes)

    @classmethod
    def desde_texto(cls, texto):
        hosts = set()
        redes = []
        for entrada in (texto or '').replace(',', ' ').split():
            try:
                redes.append(ipaddress.ip_network(entrada, strict=False))
                continue
            except ValueError:
                pass
            host = _normalizar_host(entrada)
            if host and '/' not in host:
                hosts.add(host)
            else:
                logger.warning('SITIO_EXTERNO_ALLOWLIST: entrada inválida ignorada: %s', entrada)
        return cls(hosts, redes)

    def permite_host(self, host):
        return _normalizar_host(host) in self.hosts

    def permite_ip(self, ip):
        return any(ip.version == red.version and ip in red for red in self.redes)


def obtener_allowlist():
    from constance import config
    return AllowList.desde_texto(config.SITIO_EXTERNO_ALLOWLIST)


def _normalizar_host(host):
    host = (host or '').strip().lower().rstrip('.')
    if host.startswith('[') and host.endswith(']'):
        host = host[1:-1]
    return host


def _ipv4_embebida(ip):
    """ Devuelve la IPv4 contenida en una IPv6 (mapped, 6to4, NAT64) si la hay """
    if ip.version != 6:
        return None
    if ip.ipv4_mapped:
        return ip.ipv4_mapped
    if ip.sixtofour:
        return ip.sixtofour
    if ip in NAT64_PREFIX:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return None


def es_ip_publica(ip):
    embebida = _ipv4_embebida(ip)
    if embebida is not None:
        return es_ip_publica(embebida)
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_loopback or
                                 ip.is_link_local or ip.is_unspecified or ip.is_private)


def ip_permitida(ip, allowlist):
    if allowlist.permite_ip(ip):
        return True
    embebida = _ipv4_embebida(ip)
    if embebida is not None and allowlist.permite_ip(embebida):
        return True
    return es_ip_publica(ip)


def resolver_y_validar(host, port, allowlist):
    """
    Resuelve el host y devuelve la lista de resultados de getaddrinfo, validados.
    Lanza DestinoNoPermitidoError si alguna de las IPs resueltas no está permitida.
    """
    host = _normalizar_host(host)
    if not host:
        raise DestinoNoPermitidoError(_('La URL no tiene un host válido'))
    try:
        resultados = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        raise DestinoNoPermitidoError(_('No se pudo resolver el host de la URL'))
    if not resultados:
        raise DestinoNoPermitidoError(_('No se pudo resolver el host de la URL'))
    if allowlist.permite_host(host):
        return resultados
    for resultado in resultados:
        # sockaddr[0] puede incluir scope id en IPv6 ("fe80::1%eth0")
        ip = ipaddress.ip_address(resultado[4][0].split('%')[0])
        if not ip_permitida(ip, allowlist):
            logger.warning('Sitio Externo: destino bloqueado %s (%s)', host, ip)
            raise DestinoNoPermitidoError(
                _('La URL apunta a una dirección interna no habilitada. Si el destino '
                  'es legítimo, un administrador debe agregarlo a SITIO_EXTERNO_ALLOWLIST'))
    return resultados


def validar_url(url, allowlist=None):
    """ Validación previa de una URL (al guardar). Lanza DestinoNoPermitidoError. """
    if allowlist is None:
        allowlist = obtener_allowlist()
    try:
        partes = urlsplit(url)
        port = partes.port
    except ValueError:
        raise DestinoNoPermitidoError(_('URL inválida'))
    if partes.scheme.lower() not in ESQUEMAS_PERMITIDOS:
        raise DestinoNoPermitidoError(_('Sólo se permiten URLs http o https'))
    if port is None:
        port = 443 if partes.scheme.lower() == 'https' else 80
    resolver_y_validar(partes.hostname, port, allowlist)


class _ConexionSeguraMixin(object):
    allowlist = AllowList()

    def _new_conn(self):
        resultados = resolver_y_validar(self._dns_host, self.port, self.allowlist)
        extra_kw = {}
        if self.source_address:
            extra_kw['source_address'] = self.source_address
        error = None
        # Se conecta directamente a las IPs ya validadas. El SNI y la verificación del
        # certificado siguen usando el hostname original.
        for familia, tipo, proto, _canonname, sockaddr in resultados:
            sock = None
            try:
                sock = socket.socket(familia, tipo, proto)
                for opcion in (self.socket_options or []):
                    sock.setsockopt(*opcion)
                if self.timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                    sock.settimeout(self.timeout)
                if 'source_address' in extra_kw:
                    sock.bind(extra_kw['source_address'])
                sock.connect(sockaddr)
                return sock
            except socket.timeout:
                if sock is not None:
                    sock.close()
                raise ConnectTimeoutError(
                    self, 'Connection to %s timed out. (connect timeout=%s)' %
                    (self.host, self.timeout))
            except OSError as e:
                error = e
                if sock is not None:
                    sock.close()
        raise NewConnectionError(self, 'Failed to establish a new connection: %s' % error)


class _AdapterSeguro(HTTPAdapter):

    def __init__(self, allowlist, **kwargs):
        self._allowlist = allowlist
        super(_AdapterSeguro, self).__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        super(_AdapterSeguro, self).init_poolmanager(*args, **kwargs)
        attrs = {'allowlist': self._allowlist}
        http_conn = type('HTTPConnectionSegura', (_ConexionSeguraMixin, HTTPConnection), attrs)
        https_conn = type('HTTPSConnectionSegura', (_ConexionSeguraMixin, HTTPSConnection), attrs)
        self.poolmanager.pool_classes_by_scheme = {
            'http': type('HTTPConnectionPoolSeguro', (HTTPConnectionPool, ),
                         {'ConnectionCls': http_conn}),
            'https': type('HTTPSConnectionPoolSeguro', (HTTPSConnectionPool, ),
                          {'ConnectionCls': https_conn}),
        }


class SesionSegura(requests.Session):
    """
    requests.Session que valida el destino de cada conexión contra la allowlist,
    no sigue redirects, ignora proxies del entorno y aplica un timeout por defecto.
    """

    def __init__(self, allowlist=None):
        super(SesionSegura, self).__init__()
        if allowlist is None:
            allowlist = obtener_allowlist()
        # Sin proxies del entorno: el proxy resolvería el destino sin validarlo
        self.trust_env = False
        self.adapters.clear()
        self.mount('https://', _AdapterSeguro(allowlist))
        self.mount('http://', _AdapterSeguro(allowlist))

    def request(self, method, url, *args, **kwargs):
        esquema = urlsplit(url).scheme.lower()
        if esquema not in ESQUEMAS_PERMITIDOS:
            raise DestinoNoPermitidoError(_('Sólo se permiten URLs http o https'))
        kwargs['allow_redirects'] = False
        kwargs.setdefault('timeout', TIMEOUT_DEFAULT)
        response = super(SesionSegura, self).request(method, url, *args, **kwargs)
        if response.is_redirect:
            logger.warning('Sitio Externo: redirect ignorado desde %s', url)
        return response
