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
import logging
import os

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from constance import config as constance_config
from api_app.utils.routes.inbound import escribir_ruta_entrante_config
from ominicontacto_app.services.queue_member_service import QueueMemberService

from ominicontacto_app.models import (Campana, Queue, User, OpcionCalificacion,
                                      SupervisorProfile, ClienteWebPhoneProfile)
from ominicontacto_app.tests.factories import (GrupoFactory, AgenteProfileFactory,
                                               # ArchivoDeAudioFactory,
                                               ActuacionVigenteFactory,
                                               FormularioFactory,
                                               FieldFormularioFactory, BaseDatosContactoFactory,
                                               ContactoFactory, CampanaFactory,
                                               NombreCalificacionFactory, PausaFactory,
                                               OpcionCalificacionFactory)
from configuracion_telefonia_app.tests.factories import (RutaSalienteFactory, TroncalSIPFactory,
                                                         PatronDeDiscadoFactory,
                                                         RutaEntranteFactory,
                                                         OrdenTroncalFactory)
from configuracion_telefonia_app.regeneracion_configuracion_telefonia import (
    SincronizadorDeConfiguracionTroncalSipEnAsterisk,
    SincronizadorDeConfiguracionDeRutaSalienteEnAsterisk)

from configuracion_telefonia_app.models import DestinoEntrante, TroncalSIP

from ominicontacto_app.services.creacion_queue import ActivacionQueueService
from ominicontacto_app.services.asterisk_service import ActivacionAgenteService
from ominicontacto_app.services.dialer import wombat_habilitado

logger = logging.getLogger(__name__)

PASSWORD = '098098ZZZ'


class Command(BaseCommand):
    """
    Se crean en BD valores mínimos para tener un entorno de desarrollo listo
    """

    help = "Valores mínimos para tener un entorno de desarrollo listo"

    def _crear_opciones_calificacion(self, campana):
        # opciones de calificacion
        OpcionCalificacionFactory(
            nombre=self.success.nombre, campana=campana, tipo=OpcionCalificacion.GESTION)
        OpcionCalificacionFactory(
            nombre=self.angry.nombre, campana=campana, tipo=OpcionCalificacion.NO_ACCION,
            formulario=None)
        OpcionCalificacionFactory(
            nombre=settings.CALIFICACION_REAGENDA, campana=campana, tipo=OpcionCalificacion.AGENDA,
            formulario=None)
        # calificaciones de bot/voicebot (usan NombreCalificacion del menú Calificación)
        OpcionCalificacionFactory(
            nombre=self.gestion_bot.nombre, campana=campana, tipo=OpcionCalificacion.GESTION)
        OpcionCalificacionFactory(
            nombre=self.contestador_bot.nombre, campana=campana,
            tipo=OpcionCalificacion.NO_ACCION, formulario=None)
        OpcionCalificacionFactory(
            nombre=self.abandon_bot.nombre, campana=campana,
            tipo=OpcionCalificacion.NO_ACCION, formulario=None)
        OpcionCalificacionFactory(
            nombre=self.schedule_call_bot.nombre, campana=campana,
            tipo=OpcionCalificacion.AGENDA, formulario=None)

    def _crear_campana_manual(self, nombre_campana, es_template=False):
        estado = Campana.ESTADO_TEMPLATE_ACTIVO if es_template else Campana.ESTADO_ACTIVA
        template_kwargs = {}
        if es_template:
            template_kwargs = {'es_template': True, 'nombre_template': nombre_campana}
        # crear campaña manual
        campana = CampanaFactory(
            nombre=nombre_campana, bd_contacto=self.bd_contacto,
            type=Campana.TYPE_MANUAL, reported_by=self.admin, estado=estado, **template_kwargs
        )
        # crear Queue para la campaña
        Queue.objects.create(
            campana=campana,
            name=campana.nombre,
            maxlen=25,
            wrapuptime=5,
            servicelevel=10,
            strategy='rrmemory',
            eventmemberstatus=True,
            eventwhencalled=True,
            ringinuse=True,
            setinterfacevar=True,
            weight=0,
            wait=25,
            auto_grabacion=True,
        )

        self._crear_opciones_calificacion(campana)

        return campana

    def _crear_campana_entrante(self, nombre_campana, es_template=False):
        estado = Campana.ESTADO_TEMPLATE_ACTIVO if es_template else Campana.ESTADO_ACTIVA
        template_kwargs = {}
        if es_template:
            template_kwargs = {'es_template': True, 'nombre_template': nombre_campana}
        # crear campaña entrante
        campana = CampanaFactory(
            nombre=nombre_campana, bd_contacto=self.bd_contacto,
            type=Campana.TYPE_ENTRANTE, reported_by=self.admin, estado=estado, **template_kwargs
        )
        # crear Queue para la campaña
        Queue.objects.create(
            campana=campana,
            name=campana.nombre,
            maxlen=25,
            timeout=12,
            retry=5,
            wrapuptime=5,
            servicelevel=10,
            strategy='rrmemory',
            eventmemberstatus=True,
            eventwhencalled=True,
            ringinuse=True,
            setinterfacevar=True,
            weight=0,
            wait=30,
            auto_grabacion=True,
        )

        self._crear_opciones_calificacion(campana)

        return campana

    def _crear_campana_dialer(self, nombre_campana, es_template=False):
        estado = Campana.ESTADO_TEMPLATE_ACTIVO if es_template else Campana.ESTADO_ACTIVA
        template_kwargs = {}
        if es_template:
            template_kwargs = {'es_template': True, 'nombre_template': nombre_campana}
        # crear campaña dialer
        campana = CampanaFactory(
            nombre=nombre_campana, bd_contacto=self.bd_contacto,
            type=Campana.TYPE_DIALER, reported_by=self.admin, estado=estado,
            tiempo_desconexion=10, **template_kwargs
        )
        # crear Queue para la campaña
        Queue.objects.create(
            campana=campana,
            name=campana.nombre,
            maxlen=1,
            timeout=12,
            retry=5,
            wrapuptime=5,
            servicelevel=5,
            strategy='rrmemory',
            eventmemberstatus=True,
            eventwhencalled=True,
            ringinuse=True,
            setinterfacevar=True,
            weight=0,
            wait=10,
            auto_grabacion=True,
        )

        self._crear_opciones_calificacion(campana)
        ActuacionVigenteFactory(campana=campana, domingo=True, sabado=True,
                                hora_desde='00:00', hora_hasta='23:59:59')

        return campana

    def _crear_campana_preview(self, nombre_campana, bd_contacto, es_template=False):
        # crear campaña preview
        estado = Campana.ESTADO_ACTIVA
        if es_template:
            estado = Campana.ESTADO_TEMPLATE_ACTIVO
        template_kwargs = {}
        if es_template:
            template_kwargs = {'es_template': True, 'nombre_template': nombre_campana}
        campana = CampanaFactory(
            nombre=nombre_campana, bd_contacto=bd_contacto,
            type=Campana.TYPE_PREVIEW, reported_by=self.admin, estado=estado, **template_kwargs
        )
        # crear Queue para la campaña
        Queue.objects.create(
            campana=campana,
            name=campana.nombre,
            maxlen=1,
            timeout=12,
            retry=5,
            wrapuptime=5,
            servicelevel=5,
            strategy='rrmemory',
            eventmemberstatus=True,
            eventwhencalled=True,
            ringinuse=True,
            setinterfacevar=True,
            weight=0,
            wait=10,
            auto_grabacion=True,
        )
        self._crear_opciones_calificacion(campana)

        if not es_template:
            campana.establecer_valores_iniciales_agente_contacto(False, False)

        return campana

    def _crear_ruta_entrante(self, campana_entrante, telefono):
        destino_campana_entrante = DestinoEntrante.crear_nodo_ruta_entrante(
            campana_entrante)
        ruta_entrante = RutaEntranteFactory(
            telefono=telefono, destino=destino_campana_entrante, prefijo_caller_id='')
        escribir_ruta_entrante_config(self, ruta_entrante)

    def _crear_agentes(self, cantidad, grupo, troncal_voicebot=None):
        # Crea la cantidad solicitada de agentes (mínimo 2)
        cantidad = max(2, cantidad)
        agentes_creados = []
        for i in range(0, cantidad):
            username = f'ag{i+1}'
            agente = self._crear_agente(grupo, username, PASSWORD)
            agentes_creados.append(agente)

        # Crear agente voicebot (TroncalSIP_Voicebot_Verloop, extensión 1066)
        agente_voicebot = self._crear_agente(
            grupo, 'voicebot', PASSWORD, voicebot=True,
            voicebot_trunk=troncal_voicebot, voicebot_extension=1066
        )
        agentes_creados.append(agente_voicebot)

        asterisk_sip_service = ActivacionAgenteService()
        asterisk_sip_service.activar()

        return agentes_creados

    def _crear_agente(self, grupo, username, password, voicebot=False,
                      voicebot_trunk=None, voicebot_extension=None):
        agente = AgenteProfileFactory(grupo=grupo, reported_by=self.admin)
        agente.user.username = username
        agente.user.set_password(password)
        agente.sip_extension = 1000 + agente.user.id
        agente.user.is_agente = True
        agente.voicebot = voicebot
        if voicebot:
            agente.user.first_name = 'verloop'
            agente.user.last_name = 'verloop'
            if voicebot_trunk is not None and voicebot_extension is not None:
                agente.voicebot_trunk = voicebot_trunk
                agente.voicebot_extension = voicebot_extension
        agente.user.save()
        agente.save()
        agente.user.groups.add(Group.objects.get(name='Agente'))
        
        # Crear DestinoEntrante para el agente (necesario para voicebot)
        DestinoEntrante.objects.create(
            nombre=username,
            tipo=DestinoEntrante.AGENTE,
            content_object=agente
        )
        
        return agente

    def _crear_gerente(self, username):
        user = User.objects.create_user(
            username=username,
            email=username + '@example.com',
            password=PASSWORD,
            is_supervisor=True,
            first_name='Gerente',
            last_name=username
        )
        user.groups.set([Group.objects.get(name=User.GERENTE)])
        SupervisorProfile.objects.create(
            user=user,
            sip_extension=1000 + user.id,
            sip_password="sdsfhdfhfdhfd",
            is_administrador=False,
            is_customer=False,
        )
        return user

    def _crear_supervisores(self, cantidad):
        for i in range(0, cantidad):
            username = f'ftsup{i+1}'
            self._crear_supervisor(username)

    def _crear_supervisor(self, username):
        user = User.objects.create_user(
            username=username,
            email=username + '@example.com',
            password=PASSWORD,
            is_supervisor=True,
            first_name=username,
            last_name=username
        )
        user.groups.set([Group.objects.get(name=User.SUPERVISOR)])
        SupervisorProfile.objects.create(
            user=user,
            sip_extension=1000 + user.id,
            sip_password="sdsfhdfhfdhfd",
            is_administrador=False,
            is_customer=False,
        )
        return user

    def _crear_cliente_webphone(self, username):
        user = User.objects.create_user(
            username=username,
            email=username + '@example.com',
            password=PASSWORD,
            is_supervisor=False,
            first_name='WebphoneClient',
            last_name=username,
            is_cliente_webphone=True
        )
        user.groups.set([Group.objects.get(name=User.CLIENTE_WEBPHONE)])
        cliente_webphone = ClienteWebPhoneProfile(user=user, sip_extension=1000 + user.id)
        cliente_webphone.save()
        return user

    def _crear_dbs_contactos(self):
        # crear BD default (100 contactos)
        self.bd_contacto = BaseDatosContactoFactory()
        ContactoFactory.create_batch(100, bd_contacto=self.bd_contacto)

        # Crear DBs Preview
        metadata = '{"cant_col": 4, "cols_telefono": [0], ' + \
            '"nombres_de_columnas": ["telefono", "nombre", "direccion", "localidad"]}'
        self.bd_contacto_prw1 = BaseDatosContactoFactory(
            nombre='PRW1', nombre_archivo_importacion='',
            metadata=metadata, cantidad_contactos=7
        )
        ContactoFactory(bd_contacto=self.bd_contacto_prw1, telefono='123456721',
                        datos='["Jorge Success", "CORD", "SANLUIS"]')
        ContactoFactory(bd_contacto=self.bd_contacto_prw1, telefono='88887777',
                        datos='["Luis Blacklist","CATAMARCASUR178","SANJUAN"]')
        ContactoFactory(bd_contacto=self.bd_contacto_prw1, telefono='9999',
                        datos='["Graciela No Route","NAVARROSUR1132S","SANJUAN"]')
        ContactoFactory(bd_contacto=self.bd_contacto_prw1, telefono='123456729',
                        datos='["Alfredo Congestion","ABERASTAINSUR655","SANJUAN"]')
        ContactoFactory(bd_contacto=self.bd_contacto_prw1, telefono='123456725',
                        datos='["Oscar No Answer","CATAMARCASUR178","SANJUAN"]')
        ContactoFactory(bd_contacto=self.bd_contacto_prw1, telefono='123456720',
                        datos='["Cecilia Busy","CATAMARCASUR178","SANJUAN"]')
        ContactoFactory(bd_contacto=self.bd_contacto_prw1, telefono='123456725',
                        datos='["Ricardo Cancel","ABERASTAINSUR655","SANJUAN"]')

        self.bd_contacto_prw_success = BaseDatosContactoFactory(
            nombre='PRW1-SUCCESS', nombre_archivo_importacion='',
            metadata=metadata, cantidad_contactos=7
        )
        ContactoFactory(bd_contacto=self.bd_contacto_prw_success, telefono='123456721',
                        datos='["Jorge Success", "CORD", "SANLUIS"]')
        ContactoFactory(bd_contacto=self.bd_contacto_prw_success, telefono='123456731',
                        datos='["Luis Blacklist","CATAMARCASUR178","SANJUAN"]')
        ContactoFactory(bd_contacto=self.bd_contacto_prw_success, telefono='123456741',
                        datos='["Graciela No Route","NAVARROSUR1132S","SANJUAN"]')
        ContactoFactory(bd_contacto=self.bd_contacto_prw_success, telefono='123456751',
                        datos='["Alfredo Congestion","ABERASTAINSUR655","SANJUAN"]')
        ContactoFactory(bd_contacto=self.bd_contacto_prw_success, telefono='123456761',
                        datos='["Oscar No Answer","CATAMARCASUR178","SANJUAN"]')
        ContactoFactory(bd_contacto=self.bd_contacto_prw_success, telefono='123456771',
                        datos='["Cecilia Busy","CATAMARCASUR178","SANJUAN"]')
        ContactoFactory(bd_contacto=self.bd_contacto_prw_success, telefono='123456781',
                        datos='["Ricardo Cancel","ABERASTAINSUR655","SANJUAN"]')

    def _crear_datos_entorno(self, qa_devops, qa_agents, qa_supervisors):

        self.admin = User.objects.filter(is_staff=True).first()
        self.gerente = self._crear_gerente('gerente')
        self.cliente_webphone = self._crear_cliente_webphone('webphone_user')
        self._crear_supervisores(max(0, qa_supervisors))

        # crear grupo
        grupo = GrupoFactory(auto_unpause=0)

        # 1) Troncal para la Ruta saliente (PBX emulator)
        caller_id_saliente = '01177660010'
        remote_host_saliente = 'pbxemulator:5070'
        text_config_ruta_saliente = (
            "endpoint/from_user=" + caller_id_saliente + "\n"
            "remote_hosts=" + remote_host_saliente + "\n"        
            "outbound_auth/username=" + caller_id_saliente + "\n"
            "outbound_auth/password=omnileads\n"
            "registration/contact_user=" + caller_id_saliente + "\n"
        )
        troncal_ruta_saliente = TroncalSIPFactory(
            nombre='TroncalSIP_Ruta_Saliente',
            text_config=text_config_ruta_saliente, canales_maximos=1000, tecnologia=1,
            caller_id=caller_id_saliente)
        sincronizador_troncal = SincronizadorDeConfiguracionTroncalSipEnAsterisk()
        sincronizador_troncal.regenerar_troncales(troncal_ruta_saliente)

        # 2) Troncal para el voicebot Verloop
        caller_id_voicebot = ''
        remote_host_voicebot = 'pbxemulator:5070'
        text_config_voicebot = (
            "endpoint/from_user=" + caller_id_saliente + "\n"
            "remote_hosts=" + remote_host_saliente + "\n"        
            "outbound_auth/username=" + caller_id_saliente + "\n"
            "outbound_auth/password=omnileads\n"
            "registration/contact_user=" + caller_id_saliente + "\n"
        )
        troncal_voicebot_verloop = TroncalSIPFactory(
            nombre='TroncalSIP_Voicebot_Verloop',
            text_config=text_config_voicebot, canales_maximos=1000, tecnologia=1,
            caller_id=caller_id_voicebot)
        sincronizador_troncal.regenerar_troncales(troncal_voicebot_verloop)

        agentes_creados = self._crear_agentes(
            qa_agents, grupo, troncal_voicebot=troncal_voicebot_verloop)
        # Diccionario ag1..ag10 -> AgenteProfile (excluye voicebot que está al final)
        agentes_por_nombre = {
            ag.user.username: ag for ag in agentes_creados
            if ag.user.username.startswith('ag')
        }
        agentes_base = [agentes_creados[0], agentes_creados[1]]

        if not os.getenv('WEBPHONE_CLIENT_VERSION', '') == '':
            constance_config.WEBPHONE_CLIENT_ENABLED = True

        asterisk_sip_service = ActivacionAgenteService()
        asterisk_sip_service.activar()

        # crear audio
        # ArchivoDeAudioFactory()

        # crear pausa
        PausaFactory(nombre="break", tipo='R')
        PausaFactory(nombre="gestion", tipo='P')
        PausaFactory(nombre="Pausa_0", tipo='P')

        # crear formulario (2 campos)
        form = FormularioFactory()
        FieldFormularioFactory.create_batch(2, formulario=form)

        # crear califs.(1 gestion y 1 normal) y calificaciones _BOT (menú Calificación)
        self.success = NombreCalificacionFactory(nombre='Success')
        self.success = NombreCalificacionFactory(nombre='ventas_Lee PLC')
        self.angry = NombreCalificacionFactory(nombre='hangup')
        self.gestion_bot = NombreCalificacionFactory(nombre='GESTION_BOT')
        self.contestador_bot = NombreCalificacionFactory(nombre='CONTESTADOR_BOT')
        self.abandon_bot = NombreCalificacionFactory(nombre='ABANDON_BOT')
        self.schedule_call_bot = NombreCalificacionFactory(nombre='SCHEDULE_CALL_BOT')

        self._crear_dbs_contactos()

        # Crear campañas
        campana_manual = self._crear_campana_manual('test_manual_01')

        # 4 campañas entrantes
        campana_inbound_1 = self._crear_campana_entrante('inbound-1')
        campana_inbound_2 = self._crear_campana_entrante('inbound-2')
        campana_inbound_3 = self._crear_campana_entrante('inbound-3')
        campana_inbound_4 = self._crear_campana_entrante('inbound-4')
        campana_inbound_2.videocall_habilitada = True
        campana_inbound_2.save()

        # 2 campañas preview
        campana_preview_1 = self._crear_campana_preview('preview-1', self.bd_contacto)
        campana_preview_2 = self._crear_campana_preview('preview-2', self.bd_contacto)

        # 3 campañas dialer (solo si wombat no está habilitado)
        campana_dialer_1 = None
        campana_dialer_2 = None
        campana_dialer_3 = None
        if not wombat_habilitado():
            campana_dialer_1 = self._crear_campana_dialer('dialer-1')
            campana_dialer_2 = self._crear_campana_dialer('dialer-2')
            campana_dialer_3 = self._crear_campana_dialer('dialer-3')
            self._crear_campana_dialer('DIALER_TEMPLATE', es_template=True)

        # Templates
        self._crear_campana_preview('PRW_TEMPLATE', self.bd_contacto_prw1, True)
        self._crear_campana_preview('PRW_SUCCESS_TEMPLATE', self.bd_contacto_prw_success, True)
        self._crear_campana_manual('MANUAL_TEMPLATE', es_template=True)
        self._crear_campana_entrante('INBOUND_TEMPLATE', es_template=True)

        activacion_queue_service = ActivacionQueueService()
        activacion_queue_service.activar_campanas()

        # Ruta saliente hacia el pbx-emulator (usa troncal dedicada para ruta saliente)
        ruta_saliente = RutaSalienteFactory(ring_time=25, dial_options="Tt")
        PatronDeDiscadoFactory(ruta_saliente=ruta_saliente, match_pattern="1234567[0-9][0-9]")
        PatronDeDiscadoFactory(ruta_saliente=ruta_saliente, match_pattern="88887777")
        OrdenTroncalFactory(ruta_saliente=ruta_saliente, orden=0, troncal=troncal_ruta_saliente)
        sincronizador_ruta_saliente = SincronizadorDeConfiguracionDeRutaSalienteEnAsterisk()
        sincronizador_ruta_saliente.regenerar_asterisk(ruta_saliente)

        # Rutas entrantes para las 4 campañas entrantes
        self._crear_ruta_entrante(campana_inbound_1, '99999999' if qa_devops else '01177660010')
        self._crear_ruta_entrante(campana_inbound_2, '01177660011')
        self._crear_ruta_entrante(campana_inbound_3, '01177660012')
        self._crear_ruta_entrante(campana_inbound_4, '01177660013')

        # Asignar agentes a campañas según especificación
        queue_service = QueueMemberService()

        def _agentes(*nombres):
            return [agentes_por_nombre[n] for n in nombres if n in agentes_por_nombre]

        # Inbound: inbound-1 (ag1, ag2, ag3), inbound-2 (ag2, ag3, ag4), inbound-3 (ag5..ag8), inbound-4 (ag9, ag10)
        queue_service.agregar_agentes_en_cola(campana_inbound_1, _agentes('ag1', 'ag2', 'ag3'))
        queue_service.agregar_agentes_en_cola(campana_inbound_2, _agentes('ag2', 'ag3', 'ag4'))
        queue_service.agregar_agentes_en_cola(campana_inbound_3, _agentes('ag5', 'ag6', 'ag7', 'ag8'))
        queue_service.agregar_agentes_en_cola(campana_inbound_4, _agentes('ag9', 'ag10'))

        # Preview: preview-1 (ag1..ag4), preview-2 (ag5..ag8)
        queue_service.agregar_agentes_en_cola(campana_preview_1, _agentes('ag1', 'ag2', 'ag3', 'ag4'))
        queue_service.agregar_agentes_en_cola(campana_preview_2, _agentes('ag5', 'ag6', 'ag7', 'ag8'))

        # Dialer: dialer-1 (ag1..ag4), dialer-2 (ag5..ag8), dialer-3 (ag9, ag10)
        if campana_dialer_1 is not None:
            queue_service.agregar_agentes_en_cola(campana_dialer_1, _agentes('ag1', 'ag2', 'ag3', 'ag4'))
            queue_service.agregar_agentes_en_cola(campana_dialer_2, _agentes('ag5', 'ag6', 'ag7', 'ag8'))
            queue_service.agregar_agentes_en_cola(campana_dialer_3, _agentes('ag9', 'ag10'))

        # Campaña manual con agentes base
        queue_service.agregar_agentes_en_cola(campana_manual, agentes_base)

        # Asigno campañas a gerente
        campanas_gerente = [
            campana_manual, campana_preview_1, campana_preview_2,
            campana_inbound_1, campana_inbound_2, campana_inbound_3, campana_inbound_4
        ]
        if campana_dialer_1 is not None:
            campanas_gerente.extend([campana_dialer_1, campana_dialer_2, campana_dialer_3])
        self.gerente.campanasupervisors.set(campanas_gerente)

    def add_arguments(self, parser):
        parser.add_argument(
            '--qa-devops',
            action='store_true',
            help='Initializes with QA DEVOPS configuration',
        )
        parser.add_argument(
            '--qa-agents',
            type=int,
            default=10,
            required=False,
            action='store',
            help='Número de agentes a crear (ag1, ag2, ...). Por defecto 10.',
        )
        parser.add_argument(
            '--qa-supervisors',
            type=int,
            default=0,
            required=False,
            action='store',
            help='Initializes with many Agents and Supervisors',
        )

    def handle(self, *args, **options):
        qa_devops = options['qa_devops']
        qa_agents = options['qa_agents']
        qa_supervisors = options['qa_supervisors']
        if qa_devops:
            print('Initializing with QA DEVOPS configuration')
        try:
            self._crear_datos_entorno(qa_devops, qa_agents, qa_supervisors)
            print("Some initial data created for the OML fresh installation")
        except Exception as e:
            logging.error('Fallo del comando: {0}'.format(e))
            raise CommandError('Fallo del comando: {0}'.format(e))
