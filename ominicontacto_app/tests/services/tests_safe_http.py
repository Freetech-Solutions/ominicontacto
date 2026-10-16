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
Tests de la protección contra SSRF en las interacciones con Sitios Externos
"""

from __future__ import unicode_literals

import ipaddress
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from mock import patch

from constance.test import override_config
from django.test import SimpleTestCase, TestCase

from ominicontacto_app.models import SitioExterno
from ominicontacto_app.services.sistema_externo.interaccion_sistema_externo import (
    InteraccionConSistemaExterno)
from ominicontacto_app.services.sistema_externo.safe_http import (
    AllowList, DestinoNoPermitidoError, SesionSegura, ip_permitida, validar_url)
from ominicontacto_app.tests.factories import SitioExternoFactory
from ominicontacto_app.tests.utiles import OMLBaseTest

GETADDRINFO = 'ominicontacto_app.services.sistema_externo.safe_http.socket.getaddrinfo'
IP_PUBLICA = '93.184.216.34'

_getaddrinfo_real = socket.getaddrinfo


def fake_getaddrinfo(mapeo):
    """ Resuelve los hosts de 'mapeo' a las IPs indicadas, el resto con DNS real """
    def _getaddrinfo(host, port, *args, **kwargs):
        if host in mapeo:
            ips = mapeo[host]
            if callable(ips):
                ips = ips()
            resultados = []
            for ip in ips:
                if ipaddress.ip_address(ip).version == 4:
                    resultados.append((socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, port)))
                else:
                    resultados.append(
                        (socket.AF_INET6, socket.SOCK_STREAM, 6, '', (ip, port, 0, 0)))
            return resultados
        return _getaddrinfo_real(host, port, *args, **kwargs)
    return _getaddrinfo


class _Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.server.requests_recibidos.append(self.path)
        if self.path == '/redirect':
            self.send_response(302)
            self.send_header('Location', '/destino')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        body = json.dumps(['opcion1', 'opcion2']).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_POST = do_GET

    def log_message(self, *args):
        pass


class ServidorLocalMixin(object):
    """ Levanta un servidor HTTP en 127.0.0.1 que simula un servicio interno """

    @classmethod
    def setUpClass(cls):
        super(ServidorLocalMixin, cls).setUpClass()
        cls.servidor = HTTPServer(('127.0.0.1', 0), _Handler)
        cls.servidor.requests_recibidos = []
        cls.puerto = cls.servidor.server_address[1]
        cls.hilo = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        cls.hilo.start()

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()
        super(ServidorLocalMixin, cls).tearDownClass()

    def setUp(self):
        super(ServidorLocalMixin, self).setUp()
        self.servidor.requests_recibidos.clear()

    def url_local(self, path='/', host='127.0.0.1'):
        return 'http://{0}:{1}{2}'.format(host, self.puerto, path)


class AllowListTest(SimpleTestCase):

    def test_parsea_hosts_y_redes(self):
        allowlist = AllowList.desde_texto(
            'CRM.Intranet.local., 10.20.5.0/24\n192.168.1.10  fd00::/8')
        self.assertTrue(allowlist.permite_host('crm.intranet.local'))
        self.assertTrue(allowlist.permite_ip(ipaddress.ip_address('10.20.5.77')))
        self.assertTrue(allowlist.permite_ip(ipaddress.ip_address('192.168.1.10')))
        self.assertTrue(allowlist.permite_ip(ipaddress.ip_address('fd00::1')))
        self.assertFalse(allowlist.permite_ip(ipaddress.ip_address('10.20.6.1')))
        self.assertFalse(allowlist.permite_host('otro.intranet.local'))

    def test_ignora_entradas_invalidas(self):
        allowlist = AllowList.desde_texto('10.0.0.0/33, a/b, ')
        self.assertEqual(allowlist.redes, ())
        self.assertEqual(allowlist.hosts, frozenset())

    def test_texto_vacio(self):
        allowlist = AllowList.desde_texto(None)
        self.assertEqual(allowlist.redes, ())
        self.assertEqual(allowlist.hosts, frozenset())


class IpPermitidaTest(SimpleTestCase):

    BLOQUEADAS = [
        '127.0.0.1', '10.1.2.3', '172.16.0.1', '192.168.0.1', '169.254.169.254',
        '100.64.0.1', '0.0.0.0', '224.0.0.1', '255.255.255.255', '240.0.0.1',
        '::1', '::', 'fc00::1', 'fe80::1', 'ff02::1',
        '::ffff:10.0.0.1',     # IPv4-mapped
        '2002:a00:1::1',       # 6to4 de 10.0.0.1
        '64:ff9b::a00:1',      # NAT64 de 10.0.0.1
    ]
    PERMITIDAS = ['8.8.8.8', IP_PUBLICA, '2001:4860:4860::8888', '::ffff:8.8.8.8']

    def test_bloquea_ips_no_publicas(self):
        for ip in self.BLOQUEADAS:
            with self.subTest(ip=ip):
                self.assertFalse(ip_permitida(ipaddress.ip_address(ip), AllowList()))

    def test_permite_ips_publicas(self):
        for ip in self.PERMITIDAS:
            with self.subTest(ip=ip):
                self.assertTrue(ip_permitida(ipaddress.ip_address(ip), AllowList()))

    def test_allowlist_habilita_ips_privadas(self):
        allowlist = AllowList.desde_texto('10.0.0.0/8, 169.254.169.254')
        self.assertTrue(ip_permitida(ipaddress.ip_address('10.1.2.3'), allowlist))
        self.assertTrue(ip_permitida(ipaddress.ip_address('::ffff:10.0.0.1'), allowlist))
        self.assertTrue(ip_permitida(ipaddress.ip_address('169.254.169.254'), allowlist))
        self.assertFalse(ip_permitida(ipaddress.ip_address('192.168.0.1'), allowlist))


class ValidarUrlTest(TestCase):

    def test_bloquea_esquemas_no_http(self):
        for url in ['file:///etc/passwd', 'gopher://127.0.0.1:6379/_', 'ftp://8.8.8.8/',
                    'dict://8.8.8.8:11211/']:
            with self.subTest(url=url):
                with self.assertRaises(DestinoNoPermitidoError):
                    validar_url(url, AllowList())

    def test_bloquea_ips_privadas_en_distintas_notaciones(self):
        for url in ['http://127.0.0.1/', 'http://localhost:8000/', 'http://2130706433/',
                    'http://127.1/', 'http://[::1]/', 'http://[::ffff:127.0.0.1]/',
                    'https://169.254.169.254/latest/meta-data/', 'http://0.0.0.0:6379/',
                    'http://10.0.0.1:5432/', 'http://localhost./']:
            with self.subTest(url=url):
                with self.assertRaises(DestinoNoPermitidoError):
                    validar_url(url, AllowList())

    def test_bloquea_url_sin_host(self):
        with self.assertRaises(DestinoNoPermitidoError):
            validar_url('http:///path', AllowList())

    def test_bloquea_host_que_no_resuelve(self):
        with patch(GETADDRINFO, side_effect=socket.gaierror):
            with self.assertRaises(DestinoNoPermitidoError):
                validar_url('http://no-existe.invalid/', AllowList())

    def test_bloquea_hostname_que_resuelve_a_ip_privada(self):
        with patch(GETADDRINFO, fake_getaddrinfo({'crm.ejemplo.com': ['10.0.0.5']})):
            with self.assertRaises(DestinoNoPermitidoError):
                validar_url('https://crm.ejemplo.com/api', AllowList())

    def test_bloquea_si_alguna_de_las_ips_resueltas_es_privada(self):
        mapeo = {'crm.ejemplo.com': [IP_PUBLICA, '127.0.0.1']}
        with patch(GETADDRINFO, fake_getaddrinfo(mapeo)):
            with self.assertRaises(DestinoNoPermitidoError):
                validar_url('https://crm.ejemplo.com/api', AllowList())

    def test_permite_hostname_publico(self):
        with patch(GETADDRINFO, fake_getaddrinfo({'crm.ejemplo.com': [IP_PUBLICA]})):
            validar_url('https://crm.ejemplo.com/api', AllowList())

    def test_permite_destino_privado_en_allowlist_por_red(self):
        with patch(GETADDRINFO, fake_getaddrinfo({'crm.intranet': ['10.20.5.7']})):
            validar_url('http://crm.intranet/api', AllowList.desde_texto('10.20.5.0/24'))

    def test_permite_destino_privado_en_allowlist_por_host(self):
        with patch(GETADDRINFO, fake_getaddrinfo({'crm.intranet': ['10.20.5.7']})):
            validar_url('http://CRM.intranet/api', AllowList.desde_texto('crm.intranet'))

    @override_config(SITIO_EXTERNO_ALLOWLIST='127.0.0.0/8')
    def test_usa_allowlist_de_constance(self):
        validar_url('http://127.0.0.1/')


class SesionSeguraTest(ServidorLocalMixin, TestCase):

    def test_bloquea_conexion_a_ip_privada(self):
        with self.assertRaises(DestinoNoPermitidoError):
            SesionSegura(AllowList()).get(self.url_local())
        self.assertEqual(self.servidor.requests_recibidos, [])

    def test_bloquea_post_a_ip_privada(self):
        with self.assertRaises(DestinoNoPermitidoError):
            SesionSegura(AllowList()).post(self.url_local(), json={'a': 1})
        self.assertEqual(self.servidor.requests_recibidos, [])

    def test_permite_conexion_a_ip_en_allowlist(self):
        response = SesionSegura(AllowList.desde_texto('127.0.0.1')).get(self.url_local())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), ['opcion1', 'opcion2'])

    def test_no_sigue_redirects(self):
        sesion = SesionSegura(AllowList.desde_texto('127.0.0.1'))
        for metodo in (sesion.get, sesion.post):
            with self.subTest(metodo=metodo.__name__):
                self.servidor.requests_recibidos.clear()
                response = metodo(self.url_local('/redirect'), allow_redirects=True)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(self.servidor.requests_recibidos, ['/redirect'])

    def test_bloquea_dns_rebinding(self):
        # La primera resolución (al guardar) da una IP pública, la siguiente (al conectar)
        # da una IP interna.
        respuestas = iter([[IP_PUBLICA], ['127.0.0.1']])
        mapeo = {'crm.ejemplo.com': lambda: next(respuestas)}
        url = self.url_local(host='crm.ejemplo.com')
        with patch(GETADDRINFO, fake_getaddrinfo(mapeo)):
            validar_url(url, AllowList())
            with self.assertRaises(DestinoNoPermitidoError):
                SesionSegura(AllowList()).get(url)
        self.assertEqual(self.servidor.requests_recibidos, [])

    def test_conecta_a_la_ip_validada(self):
        mapeo = {'crm.intranet': ['127.0.0.1']}
        url = self.url_local(path='/ok', host='crm.intranet')
        with patch(GETADDRINFO, fake_getaddrinfo(mapeo)):
            response = SesionSegura(AllowList.desde_texto('crm.intranet')).get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.servidor.requests_recibidos, ['/ok'])

    def test_ignora_proxies_del_entorno(self):
        with patch.dict('os.environ', {'HTTP_PROXY': self.url_local(),
                                       'http_proxy': self.url_local()}):
            with self.assertRaises(DestinoNoPermitidoError):
                SesionSegura(AllowList()).get('http://10.0.0.1/')
        self.assertEqual(self.servidor.requests_recibidos, [])

    def test_bloquea_esquemas_no_http(self):
        with self.assertRaises(DestinoNoPermitidoError):
            SesionSegura(AllowList()).get('ftp://8.8.8.8/')

    @override_config(SITIO_EXTERNO_ALLOWLIST='127.0.0.1')
    def test_usa_allowlist_de_constance(self):
        response = SesionSegura().get(self.url_local())
        self.assertEqual(response.status_code, 200)


class InteraccionConSistemaExternoSeguraTest(ServidorLocalMixin, OMLBaseTest):

    def setUp(self):
        super(InteraccionConSistemaExternoSeguraTest, self).setUp()
        self.servicio = InteraccionConSistemaExterno()
        self.sitio_externo = SitioExternoFactory(
            url=self.url_local(), disparador=SitioExterno.SERVER, objetivo=None)

    def test_ejecutar_interaccion_bloquea_ip_privada(self):
        with patch.object(SitioExterno, 'get_parametros', return_value={}):
            error = self.servicio.ejecutar_interaccion(
                self.sitio_externo, None, None, None, {})
        self.assertIsInstance(error, DestinoNoPermitidoError)
        self.assertEqual(self.servidor.requests_recibidos, [])

    @override_config(SITIO_EXTERNO_ALLOWLIST='127.0.0.1')
    def test_ejecutar_interaccion_permite_ip_en_allowlist(self):
        with patch.object(SitioExterno, 'get_parametros', return_value={}):
            error = self.servicio.ejecutar_interaccion(
                self.sitio_externo, None, None, None, {})
        self.assertIsNone(error)
        self.assertEqual(len(self.servidor.requests_recibidos), 1)

    def test_obtener_lista_dinamica_bloquea_ip_privada(self):
        respuesta = self.servicio.obtener_lista_dinamica(self.sitio_externo)
        self.assertEqual(
            respuesta, ['ERROR: Service {} not available'.format(self.sitio_externo.nombre)])
        self.assertEqual(self.servidor.requests_recibidos, [])

    @override_config(SITIO_EXTERNO_ALLOWLIST='127.0.0.1')
    def test_obtener_lista_dinamica_permite_ip_en_allowlist(self):
        respuesta = self.servicio.obtener_lista_dinamica(self.sitio_externo)
        self.assertEqual(respuesta, ['opcion1', 'opcion2'])

    @override_config(SITIO_EXTERNO_ALLOWLIST='127.0.0.1')
    def test_obtener_lista_dinamica_no_sigue_redirects(self):
        self.sitio_externo.url = self.url_local('/redirect')
        respuesta = self.servicio.obtener_lista_dinamica(self.sitio_externo)
        self.assertEqual(
            respuesta, ['ERROR: Service {} not available'.format(self.sitio_externo.nombre)])
        self.assertEqual(self.servidor.requests_recibidos, ['/redirect'])

    def test_probar_autenticacion_bloquea_ip_privada(self):
        with self.assertRaises(DestinoNoPermitidoError):
            self.servicio.probar_autenticacion(
                url=self.url_local(), username='u', password='p', ssl_estricto=True,
                campo_token='token')
        self.assertEqual(self.servidor.requests_recibidos, [])

    def test_actualizar_token_bloquea_ip_privada(self):
        autenticacion = AutenticacionFalsa(url=self.url_local())
        mensaje, error = self.servicio.actualizar_token(autenticacion)
        self.assertTrue(error)
        self.assertEqual(self.servidor.requests_recibidos, [])


class AutenticacionFalsa(object):
    def __init__(self, url):
        self.url = url
        self.username = 'u'
        self.password = 'p'
        self.ssl_estricto = True
