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

"""Vistas genéricas de reportes de campañas"""

from __future__ import unicode_literals

import datetime

from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, View
from django.core import paginator as django_paginator

from ominicontacto_app.forms.base import ReporteCampanaForm

from ominicontacto_app.models import AgenteProfile, Campana, RespuestaFormularioGestion

from ominicontacto_app.services.estadisticas_campana_v2 import EstadisticasServiceV2

from ominicontacto_app.services.reporte_agente import EstadisticasAgenteService
from ominicontacto_app.services.reporte_campana_calificacion import ReporteCampanaService
from ominicontacto_app.services.reporte_campana_pdf import ReporteCampanaPDFService

from ominicontacto_app.utiles import convert_fecha_datetime, fecha_hora_local
from ominicontacto_app.services.reporte_campana_csv import (
    ExportacionArchivoCampanaCSV)
from reportes_app.reportes.reporte_llamados_contactados_csv import (
    ExportacionCampanaCSV
)
from ominicontacto_app.services.reporte_resultados_de_base_csv import (
    ExportacionReporteCSV
)
from reportes_app.reportes.reporte_nivel_servicio import ReporteNivelServicio
from reportes_app.forms import ReporteNivelServicioForm
from reportes_app.services.exportacion_canalidades_centro_contacto import (
    obtener_url_descarga_canalidades,
)
from reportes_app.services.exportacion_canalidades_egresos_centro_contacto import (
    obtener_url_descarga_canalidades_egresos,
)
from reportes_app.services.exportacion_canalidades_por_hora_centro_contacto import (
    obtener_url_descarga_canalidades_por_hora,
)
from reportes_app.services.exportacion_canalidades_por_hora_egresos_centro_contacto import (
    obtener_url_descarga_canalidades_por_hora_egresos,
)
from reportes_app.services.exportacion_canalidades_por_dia_centro_contacto import (
    obtener_url_descarga_canalidades_por_dia,
)
from reportes_app.services.exportacion_canalidades_por_dia_egresos_centro_contacto import (
    obtener_url_descarga_canalidades_por_dia_egresos,
)
from reportes_app.services.exportacion_canalidades_por_mes_centro_contacto import (
    obtener_url_descarga_canalidades_por_mes,
)
from reportes_app.services.exportacion_canalidades_por_mes_egresos_centro_contacto import (
    obtener_url_descarga_canalidades_por_mes_egresos,
)
from reportes_app.services.exportacion_llamadas_atendidas_centro_contacto import (
    obtener_url_descarga_llamadas_atendidas,
)
from reportes_app.services.exportacion_llamadas_atendidas_egresos_centro_contacto import (
    obtener_url_descarga_llamadas_atendidas_egresos,
)
from reportes_app.services.exportacion_llamadas_no_atendidas_centro_contacto import (
    obtener_url_descarga_llamadas_no_atendidas,
)
from reportes_app.services.exportacion_llamadas_no_atendidas_egresos_centro_contacto import (
    obtener_url_descarga_llamadas_no_atendidas_egresos,
)
from reportes_app.services.exportacion_llamadas_voz_centro_contacto import (
    obtener_url_descarga_llamadas_voz,
)
from reportes_app.services.exportacion_llamadas_voz_egresos_centro_contacto import (
    obtener_url_descarga_llamadas_voz_egresos,
)
from reportes_app.services.exportacion_llamadas_por_hora_centro_contacto import (
    obtener_url_descarga_llamadas_por_hora,
)
from reportes_app.services.exportacion_llamadas_por_hora_egresos_centro_contacto import (
    obtener_url_descarga_llamadas_por_hora_egresos,
)
from reportes_app.services.exportacion_llamadas_por_dia_centro_contacto import (
    obtener_url_descarga_llamadas_por_dia,
)
from reportes_app.services.exportacion_llamadas_por_dia_egresos_centro_contacto import (
    obtener_url_descarga_llamadas_por_dia_egresos,
)
from reportes_app.services.exportacion_llamadas_por_mes_centro_contacto import (
    obtener_url_descarga_llamadas_por_mes,
)
from reportes_app.services.exportacion_llamadas_por_mes_egresos_centro_contacto import (
    obtener_url_descarga_llamadas_por_mes_egresos,
)
from reportes_app.services.exportacion_conversaciones_respondidas_centro_contacto import (
    obtener_url_descarga_conversaciones_respondidas,
)
from reportes_app.services.exportacion_conversaciones_respondidas_egresos_centro_contacto import (
    obtener_url_descarga_conversaciones_respondidas_egresos,
)
from reportes_app.services.exportacion_conversaciones_no_respondidas_centro_contacto import (
    obtener_url_descarga_conversaciones_no_respondidas,
)
from reportes_app.services.exportacion_conversaciones_no_respondidas_egresos_centro_contacto import (
    obtener_url_descarga_conversaciones_no_respondidas_egresos,
)
from reportes_app.services.exportacion_whatsapp_mensajes_por_hora_centro_contacto import (
    obtener_url_descarga_whatsapp_mensajes_por_hora,
)
from reportes_app.services.exportacion_whatsapp_mensajes_por_hora_egresos_centro_contacto import (
    obtener_url_descarga_whatsapp_mensajes_por_hora_egresos,
)
from reportes_app.services.exportacion_whatsapp_mensajes_por_campana_centro_contacto import (
    obtener_url_descarga_whatsapp_mensajes_por_campana,
)
from reportes_app.services.exportacion_whatsapp_mensajes_por_campana_egresos_centro_contacto import (
    obtener_url_descarga_whatsapp_mensajes_por_campana_egresos,
)
from reportes_app.services.exportacion_whatsapp_mensajes_por_dia_centro_contacto import (
    obtener_url_descarga_whatsapp_mensajes_por_dia,
)
from reportes_app.services.exportacion_whatsapp_mensajes_por_dia_egresos_centro_contacto import (
    obtener_url_descarga_whatsapp_mensajes_por_dia_egresos,
)
from reportes_app.services.exportacion_whatsapp_mensajes_por_mes_centro_contacto import (
    obtener_url_descarga_whatsapp_mensajes_por_mes,
)
from reportes_app.services.exportacion_whatsapp_mensajes_por_mes_egresos_centro_contacto import (
    obtener_url_descarga_whatsapp_mensajes_por_mes_egresos,
)
from reportes_app.services.exportacion_agents_activity_v2_listado import (
    obtener_url_descarga_agents_activity_v2_listado,
)


class CampanaReporteCalificacionListView(FormView):
    """
    Muestra un listado de contactos a los cuales se los calificaron en la campana
    """
    template_name = 'calificaciones_campana.html'
    context_object_name = 'campana'
    model = Campana
    form_class = ReporteCampanaForm
    campana = None

    def get_object(self, queryset=None):
        if self.campana is None:
            user = self.request.user
            asignadas = Campana.objects.all()
            if not user.get_is_administrador():
                supervisor = user.get_supervisor_profile()
                asignadas = supervisor.campanas_asignadas()
            self.campana = asignadas.get(pk=self.kwargs['pk_campana'])
        return self.campana

    def get(self, request, *args, **kwargs):
        user = request.user
        asignadas = Campana.objects.all()

        if not user.get_is_administrador():
            supervisor = user.get_supervisor_profile()
            asignadas = supervisor.campanas_asignadas_actuales()

        try:
            self.campana = asignadas.get(pk=self.kwargs['pk_campana'])
            hoy_ahora = fecha_hora_local(timezone.now())
            hoy = hoy_ahora.date()
            fecha_desde = fecha_hora_local(datetime.datetime.combine(hoy, datetime.time.min))
            fecha_hasta = fecha_hora_local(datetime.datetime.combine(hoy_ahora, datetime.time.max))
            service = ReporteCampanaService(self.get_object())
            service.calificaciones_por_fechas(fecha_desde, fecha_hasta)
            historico_calificaciones_qs = service.historico_calificaciones_qs
            historico_calidficaciones = self._procesa_historico_calificaciones(
                historico_calificaciones_qs, fecha_desde, fecha_hasta)
            return self.render_to_response(self.get_context_data(
                historico_calificaciones=historico_calidficaciones.values()))
        except Campana.DoesNotExist:
            messages.warning(self.request, _(u"Usted no puede acceder a esta campaña."))
            return redirect('index')

    def get_context_data(self, **kwargs):
        context = super(CampanaReporteCalificacionListView, self).get_context_data(
            **kwargs)
        context['campana'] = self.get_object()
        context['calificaciones_task_id'] = get_random_string(8)
        context['formulario_gestion_task_id'] = get_random_string(8)

        historico_calificaciones = []

        if 'historico_calificaciones' in context:
            historico_calificaciones = context['historico_calificaciones']

        qs = list(historico_calificaciones)

        if 'pagina' in context and context['pagina']:
            page = context['pagina']
        else:
            page = 1

        if 'calificaciones_x_pagina' in context:
            calificaciones_x_pagina = context['calificaciones_x_pagina']
        else:
            calificaciones_x_pagina = 2

        result_paginator = django_paginator.Paginator(qs, calificaciones_x_pagina)
        try:
            qs = result_paginator.page(page)
        except django_paginator.PageNotAnInteger:
            qs = result_paginator.page(1)
        except django_paginator.EmptyPage:
            qs = result_paginator.page(result_paginator.num_pages)

        num_pages = result_paginator.num_pages
        page_no = int(page)
        if num_pages <= 7 or page_no <= 4:  # case 1 and 2
            pages = [x for x in range(1, min(num_pages + 1, 8))]
        elif page_no > num_pages - 4:  # case 4
            pages = [x for x in range(num_pages - 6, num_pages + 1)]
        else:  # case 3
            pages = [x for x in range(page_no - 3, page_no + 4)]
        context.update({'pages': pages})
        # ----- </Paginate> -----
        context['historico_calificaciones'] = qs
        return context

    def _procesa_historico_calificaciones(
            self, historico_calificaciones_qs, fecha_desde, fecha_hasta):
        res = {}
        for hc in list(historico_calificaciones_qs):
            if hc.id not in res:
                res[hc.id] = {}
                res[hc.id]['id'] = hc.id
                res[hc.id]['telefono'] = hc.contacto.telefono
                res[hc.id]['datos'] = hc.contacto.datos
                res[hc.id]['cals'] = {}
                res[hc.id]['calif_actual'] = {}
                res[hc.id]['tiene_historico'] = False

            nombre = hc.opcion_calificacion.nombre
            if hc.opcion_calificacion.es_agenda():
                nombre = "{} {}".format(nombre, hc.get_tipo_agenda_display())
            res[hc.id]['cals'][hc.history_id] = {
                'nombre': nombre,
                'observaciones': hc.observaciones,
                'subcalificacion': hc.subcalificacion,
                'fecha_hora': timezone.localtime(hc.history_date).strftime("%Y/%m/%d %H:%M:%S"),
                'history_id': hc.history_id,
            }

            if res[hc.id]['calif_actual'] == {}:
                res[hc.id]['calif_actual'] = res[hc.id]['cals'][hc.history_id]
            else:
                res[hc.id]['tiene_historico'] = True

        historico_formulario_gestion = RespuestaFormularioGestion.history.filter(
            history_date__range=(fecha_desde, fecha_hasta),
            calificacion__in=res.keys())

        for gestion in historico_formulario_gestion:
            if gestion.metadata is not None:
                calificacion_historica_id = gestion.history_change_reason
                if calificacion_historica_id is not None and str(calificacion_historica_id).isdigit:
                    if int(calificacion_historica_id) not in res[gestion.calificacion.id]['cals']:
                        # Evitar Problema con calificacion de un dia y la repuesta del siguiente
                        continue
                    try:
                        gestiones_list = res[gestion.calificacion.id]['cals'][int(
                            calificacion_historica_id)]['gestiones']
                    except Exception:
                        gestiones_list = []
                    gestiones_list.append(gestion.metadata.replace('\r\n', ' '))
                    res[gestion.calificacion.id]['cals'][int(calificacion_historica_id)].update({
                        'gestiones': gestiones_list
                    })
                    res[gestion.calificacion.id]['tiene_historico'] = True
        return res

    def form_valid(self, form):
        fecha = form.cleaned_data.get('fecha')
        pagina = form.cleaned_data.get('pagina')
        calificaciones_x_pagina = form.cleaned_data.get('calificaciones_x_pagina')
        fecha_desde, fecha_hasta = fecha.split('-')
        fecha_desde = convert_fecha_datetime(fecha_desde)
        fecha_hasta = convert_fecha_datetime(fecha_hasta)
        fecha_desde = datetime.datetime.combine(fecha_desde, datetime.time.min)
        fecha_hasta = datetime.datetime.combine(fecha_hasta, datetime.time.max)
        service = ReporteCampanaService(self.get_object())
        service.calificaciones_por_fechas(fecha_desde, fecha_hasta)
        historico_calificaciones_qs = service.historico_calificaciones_qs
        historico_calidficaciones = self._procesa_historico_calificaciones(
            historico_calificaciones_qs, fecha_desde, fecha_hasta)
        return self.render_to_response(self.get_context_data(
            historico_calificaciones=historico_calidficaciones.values(),
            reporte_fecha_desde_elegida=fecha_desde.strftime("%m/%d/%Y"),
            reporte_fecha_hasta_elegida=fecha_hasta.strftime("%m/%d/%Y"),
            pk_campana=self.kwargs['pk_campana'],
            pagina=pagina,
            calificaciones_x_pagina=calificaciones_x_pagina
        ))


class ExportaCampanaReporteCalificacionView(View):
    """
    Esta vista invoca a generar un csv de reporte de la campana.
    """

    model = Campana
    context_object_name = 'campana'

    def get_object(self, queryset=None):
        return Campana.objects.get(pk=self.kwargs['pk_campana'])

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        service = ExportacionArchivoCampanaCSV(self.object, "calificados")
        url = service.obtener_url_reporte_csv_descargar()
        return redirect(url)


class ExportaReporteFormularioVentaView(View):
    """
    Esta vista invoca a generar un csv de reporte de la la venta.
    """

    model = Campana
    context_object_name = 'campana'

    def get_object(self, queryset=None):
        return Campana.objects.get(pk=self.kwargs['pk_campana'])

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        service = ExportacionArchivoCampanaCSV(self.object, "formulario_gestion")
        url = service.obtener_url_reporte_csv_descargar()
        return redirect(url)


class CampanaReporteGraficoView(FormView):
    """Esta vista genera el reporte grafico de la campana"""

    context_object_name = 'campana'
    model = Campana
    form_class = ReporteCampanaForm
    template_name = 'reporte_grafico_campana.html'

    campana = None

    def get_object(self, queryset=None):
        if self.campana is None:
            user = self.request.user
            asignadas = Campana.objects.all()

            if not user.get_is_administrador():
                supervisor = user.get_supervisor_profile()
                asignadas = supervisor.campanas_asignadas()
            self.campana = asignadas.filter(
                pk=self.kwargs['pk_campana']).select_related('bd_contacto').first()
        return self.campana

    def get(self, request, *args, **kwargs):
        campana = self.get_object()
        if not campana:
            messages.warning(self.request, _(u"Usted no puede acceder a esta campaña."))
            return redirect('index')
        hoy_ahora = fecha_hora_local(timezone.now())
        hoy = hoy_ahora.date()
        fecha_desde = fecha_hora_local(datetime.datetime.combine(hoy, datetime.time.min))
        fecha_hasta = fecha_hora_local(datetime.datetime.combine(hoy_ahora, datetime.time.max))
        service = EstadisticasServiceV2(campana, fecha_desde, fecha_hasta)
        # genera los reportes grafico de la campana
        graficos_estadisticas = service.general_campana()
        # generar el reporte pdf
        service_pdf = ReporteCampanaPDFService()
        service_pdf.crea_reporte_pdf(campana, graficos_estadisticas)
        return self.render_to_response(self.get_context_data(
            graficos_estadisticas=graficos_estadisticas,
            pk_campana=self.kwargs['pk_campana']))

    def get_context_data(self, **kwargs):
        from django.conf import settings
        context = super(CampanaReporteGraficoView, self).get_context_data(
            **kwargs)
        self.campana = self.get_object()
        context['campana'] = self.campana
        context['campana_entrante'] = (self.campana.type == Campana.TYPE_ENTRANTE)
        context['task_id'] = get_random_string(8)
        # Agregar setting para verificar si es omnidialer
        context['es_omnidialer'] = (hasattr(settings, 'OML_DIALER_ENGINE') and 
                                     settings.OML_DIALER_ENGINE == 'omnidialer')
        return context

    def form_valid(self, form):
        campana = self.get_object()
        fecha = form.cleaned_data.get('fecha')
        fecha_desde, fecha_hasta = fecha.split('-')
        fecha_desde = convert_fecha_datetime(fecha_desde)
        fecha_hasta = convert_fecha_datetime(fecha_hasta, final_dia=True)
        # generar el reporte grafico de acuerdo al periodo de fecha seleccionado
        service = EstadisticasServiceV2(campana, fecha_desde, fecha_hasta)
        graficos_estadisticas = service.general_campana()
        # genera el reporte pdf de la campana
        service_pdf = ReporteCampanaPDFService()
        service_pdf.crea_reporte_pdf(campana, graficos_estadisticas)
        return self.render_to_response(self.get_context_data(
            graficos_estadisticas=graficos_estadisticas,
            reporte_fecha_desde_elegida=fecha_desde.strftime("%m/%d/%Y"),
            reporte_fecha_hasta_elegida=fecha_hasta.strftime("%m/%d/%Y"),
            pk_campana=self.kwargs['pk_campana']))


class ExportaCampanaReporteGraficoPDFView(View):
    """
    Esta vista invoca a generar un pdf de reporte de la campana
    """

    model = Campana
    context_object_name = 'campana'

    def get_object(self, queryset=None):
        return Campana.objects.get(pk=self.kwargs['pk_campana'])

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        service = ReporteCampanaPDFService()
        url = service.obtener_url_reporte_pdf_descargar(self.object)
        return redirect(url)


class ExportaReporteLlamadosContactadosView(View):
    """
    Esta vista invoca a generar un csv de reporte de la campana.
    """

    model = Campana
    context_object_name = 'campana'

    def get_object(self, queryset=None):
        return Campana.objects.get(pk=self.kwargs['pk_campana'])

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        service_csv = ExportacionCampanaCSV()
        url = service_csv.obtener_url_reporte_csv_descargar(
            self.object, "contactados")

        return redirect(url)


class ExportaReporteNoAtendidosView(View):
    """
    Esta vista invoca a generar un csv de reporte de la campana.
    """

    model = Campana
    context_object_name = 'campana'

    def get_object(self, queryset=None):
        return Campana.objects.get(pk=self.kwargs['pk_campana'])

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        service_csv = ExportacionCampanaCSV()
        url = service_csv.obtener_url_reporte_csv_descargar(
            self.object, "no_atendidos")

        return redirect(url)


class ExportaReporteCalificadosView(View):
    """
    Esta vista invoca a generar un csv de reporte de la campana.
    """

    model = Campana
    context_object_name = 'campana'

    def get_object(self, queryset=None):
        return Campana.objects.get(pk=self.kwargs['pk_campana'])

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        service_csv = ExportacionCampanaCSV()
        url = service_csv.obtener_url_reporte_csv_descargar(
            self.object, "calificados")

        return redirect(url)


class ExportaReporteCalificacionesPorAgenteView(View):
    """
    Esta vista invoca a generar un csv de calificaciones por agente de la campana.
    """

    model = Campana
    context_object_name = 'campana'

    def get_object(self, queryset=None):
        return Campana.objects.get(pk=self.kwargs['pk_campana'])

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        service_csv = ExportacionCampanaCSV()
        url = service_csv.obtener_url_reporte_csv_descargar(
            self.object, "calificaciones_por_agente")

        return redirect(url)


class ExportaReporteInteraccionesPorAgenteView(View):
    """
    Vista de descarga del CSV de interacciones por agente de la campana.
    """

    model = Campana
    context_object_name = 'campana'

    def get_object(self, queryset=None):
        return Campana.objects.get(pk=self.kwargs['pk_campana'])

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        service_csv = ExportacionCampanaCSV()
        url = service_csv.obtener_url_reporte_csv_descargar(
            self.object, "interacciones_por_agente")

        return redirect(url)


class ExportaReportePerformanceAgentesView(View):
    """
    Vista de descarga del CSV de performance de agentes de la campana.
    """

    model = Campana
    context_object_name = 'campana'

    def get_object(self, queryset=None):
        return Campana.objects.get(pk=self.kwargs['pk_campana'])

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        service_csv = ExportacionCampanaCSV()
        url = service_csv.obtener_url_reporte_csv_descargar(
            self.object, "performance_agentes")

        return redirect(url)


class ExportaReporteResultadosDeBaseView(View):
    """
    Esta vista invoca un servicio para descargar
    un csv del reporte de la campana.
    """

    model = Campana
    context_object_name = 'campana'

    def get_object(self, queryset=None):
        return Campana.objects.get(pk=self.kwargs['pk_campana'])

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        all_data = bool(int(self.kwargs['all_data']))
        service_csv = ExportacionReporteCSV()
        if all_data:
            name_report = "reporte_resultados_todos"
        else:
            name_report = "reporte_resultados"
        url = service_csv.obtener_url_reporte_csv_descargar(
            self.object,
            name_report
        )

        return redirect(url)


class AgenteCampanaReporteGrafico(FormView):
    """Esta vista genera el reporte grafico de la campana para un agente"""
    template_name = 'reporte_agente.html'
    form_class = ReporteCampanaForm

    def get_object(self, queryset=None):
        return Campana.objects.get(pk=self.kwargs['pk_campana'])

    def get(self, request, *args, **kwargs):
        service = EstadisticasAgenteService()
        hoy_ahora = datetime.datetime.today()
        hoy = hoy_ahora.date()
        agente = AgenteProfile.objects.get(pk=self.kwargs['pk_agente'])
        # generar el reporte para el agente de la campana
        graficos_estadisticas = service.general_campana(agente,
                                                        self.get_object(), hoy,
                                                        hoy_ahora)
        return self.render_to_response(self.get_context_data(
            graficos_estadisticas=graficos_estadisticas))

    def get_context_data(self, **kwargs):
        context = super(AgenteCampanaReporteGrafico, self).get_context_data(
            **kwargs)

        agente = AgenteProfile.objects.get(pk=self.kwargs['pk_agente'])
        context['pk_campana'] = self.kwargs['pk_campana']

        context['agente'] = agente
        return context

    def form_valid(self, form):
        fecha = form.cleaned_data.get('fecha')
        fecha_desde, fecha_hasta = fecha.split('-')
        fecha_desde = convert_fecha_datetime(fecha_desde)
        fecha_hasta = convert_fecha_datetime(fecha_hasta)
        # genera el reporte para el agente de esta campana
        service = EstadisticasAgenteService()
        agente = AgenteProfile.objects.get(pk=self.kwargs['pk_agente'])
        graficos_estadisticas = service.general_campana(agente,
                                                        self.get_object(),
                                                        fecha_desde,
                                                        fecha_hasta)
        return self.render_to_response(self.get_context_data(
            graficos_estadisticas=graficos_estadisticas))


class ReporteNivelServicioView(FormView):
    """
    Vista que muestra el reporte de Nivel de Servicio (Service Level)
    """
    template_name = 'reporte_nivel_servicio.html'
    form_class = ReporteNivelServicioForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        user = self.request.user
        
        # Obtener campañas asignadas según el tipo de usuario
        if user.get_is_administrador():
            campanas_asignadas = Campana.objects.obtener_actuales()
        else:
            supervisor = user.get_supervisor_profile()
            campanas_asignadas = supervisor.campanas_asignadas_actuales()
        
        kwargs['campanas_asignadas'] = campanas_asignadas
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        hoy = fecha_hora_local(timezone.now()).date()
        initial['fecha'] = ' - '.join([hoy.strftime('%d/%m/%Y')] * 2)
        initial['tiempo_objetivo'] = 20
        return initial

    def get(self, request, *args, **kwargs):
        """Muestra el reporte con datos del día actual por defecto"""
        hoy_ahora = fecha_hora_local(timezone.now())
        hoy = hoy_ahora.date()
        fecha_desde = datetime.datetime.combine(hoy, datetime.time.min)
        fecha_hasta = datetime.datetime.combine(hoy_ahora, datetime.time.max)
        
        # Obtener campañas entrantes y Dialer
        user = request.user
        if user.get_is_administrador():
            campanas = Campana.objects.obtener_actuales().filter(
                type__in=[Campana.TYPE_ENTRANTE, Campana.TYPE_DIALER])
        else:
            supervisor = user.get_supervisor_profile()
            campanas = supervisor.campanas_asignadas_actuales().filter(
                type__in=[Campana.TYPE_ENTRANTE, Campana.TYPE_DIALER])
        
        # Generar reporte
        reporte = ReporteNivelServicio(
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            campanas=campanas,
            tiempo_objetivo=20
        )
        
        return self.render_to_response(self.get_context_data(
            desde=fecha_desde,
            hasta=fecha_hasta,
            estadisticas=reporte.estadisticas,
            estadisticas_por_campana=reporte.estadisticas_por_campana,
            kpis=reporte.obtener_kpis(),
        ))

    def form_valid(self, form):
        """Procesa el formulario y genera el reporte"""
        fecha_desde = form.desde
        fecha_hasta = form.hasta
        tiempo_objetivo = form.cleaned_data.get('tiempo_objetivo', 20)
        campana_id = form.cleaned_data.get('campana')
        
        # Obtener campañas según filtro (entrantes y Dialer)
        user = self.request.user
        if user.get_is_administrador():
            campanas = Campana.objects.obtener_actuales().filter(
                type__in=[Campana.TYPE_ENTRANTE, Campana.TYPE_DIALER])
        else:
            supervisor = user.get_supervisor_profile()
            campanas = supervisor.campanas_asignadas_actuales().filter(
                type__in=[Campana.TYPE_ENTRANTE, Campana.TYPE_DIALER])
        
        # Filtrar por campaña específica si se seleccionó
        if campana_id:
            campanas = campanas.filter(id=campana_id)
        
        # Generar reporte
        reporte = ReporteNivelServicio(
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            campanas=campanas,
            tiempo_objetivo=tiempo_objetivo
        )
        
        return self.render_to_response(self.get_context_data(
            desde=fecha_desde,
            hasta=fecha_hasta,
            estadisticas=reporte.estadisticas,
            estadisticas_por_campana=reporte.estadisticas_por_campana,
            kpis=reporte.obtener_kpis(),
            tiempo_objetivo=tiempo_objetivo,
        ))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(kwargs)
        return context


class DescargarCSVCanalidadesCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Canalidades por campaña generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_canalidades(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVCanalidadesEgresosCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Canalidades por campaña (Egresos) generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_canalidades_egresos(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVCanalidadesPorHoraCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Canalidades por hora generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_canalidades_por_hora(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVCanalidadesPorHoraEgresosCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Canalidades por hora (Egresos) generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_canalidades_por_hora_egresos(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVCanalidadesPorDiaCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Canalidades por día generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_canalidades_por_dia(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVCanalidadesPorDiaEgresosCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Canalidades por día (Egresos) generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_canalidades_por_dia_egresos(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVCanalidadesPorMesCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Canalidades por mes generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_canalidades_por_mes(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVCanalidadesPorMesEgresosCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Canalidades por mes (Egresos) generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_canalidades_por_mes_egresos(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVLlamadasAtendidasCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Listado de llamadas atendidas generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_llamadas_atendidas(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVLlamadasAtendidasEgresosCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Listado de llamadas atendidas (Egresos/Voz)
    generado para task_id. El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_llamadas_atendidas_egresos(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVLlamadasNoAtendidasCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Listado de llamadas no atendidas generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_llamadas_no_atendidas(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVLlamadasNoAtendidasEgresosCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Listado de llamadas no atendidas (Egresos) generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_llamadas_no_atendidas_egresos(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVLlamadasVozCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Llamadas de voz por campaña generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_llamadas_voz(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVLlamadasVozEgresosCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Llamadas de voz por campaña (Egresos) generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_llamadas_voz_egresos(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVLlamadasPorHoraCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Llamadas por hora de día generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_llamadas_por_hora(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVLlamadasPorHoraEgresosCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Llamadas por hora de día (Egresos) generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_llamadas_por_hora_egresos(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVLlamadasPorDiaCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Llamadas por día generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_llamadas_por_dia(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVLlamadasPorDiaEgresosCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Llamadas por día (Egresos/Voz) generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_llamadas_por_dia_egresos(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVLlamadasPorMesCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Llamadas por mes generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_llamadas_por_mes(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVLlamadasPorMesEgresosCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Llamadas por mes (Egresos) generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_llamadas_por_mes_egresos(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVConversacionesRespondidasCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Conversaciones Respondidas generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_conversaciones_respondidas(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVConversacionesRespondidasEgresosCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Conversaciones Respondidas (Egresos) generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_conversaciones_respondidas_egresos(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVConversacionesNoRespondidasCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Conversaciones no respondidas generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_conversaciones_no_respondidas(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVConversacionesNoRespondidasEgresosCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Conversaciones no respondidas (Egresos) generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_conversaciones_no_respondidas_egresos(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVWhatsappMensajesPorHoraCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Mensajes por hora de día (WhatsApp) generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_whatsapp_mensajes_por_hora(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVWhatsappMensajesPorHoraEgresosCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Mensajes por hora (WhatsApp Egresos) generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_whatsapp_mensajes_por_hora_egresos(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVWhatsappMensajesPorCampanaCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Mensajes por campaña (WhatsApp Ingresos) generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_whatsapp_mensajes_por_campana(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVWhatsappMensajesPorCampanaEgresosCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Mensajes por campaña (WhatsApp Egresos) generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_whatsapp_mensajes_por_campana_egresos(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVWhatsappMensajesPorDiaCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Mensajes por día (WhatsApp Ingresos) generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_whatsapp_mensajes_por_dia(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVWhatsappMensajesPorDiaEgresosCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Mensajes por día (WhatsApp Egresos) generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_whatsapp_mensajes_por_dia_egresos(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVWhatsappMensajesPorMesCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Mensajes por mes (WhatsApp Ingresos) generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_whatsapp_mensajes_por_mes(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVWhatsappMensajesPorMesEgresosCentroContactoView(View):
    """
    GET: redirige al archivo CSV de Mensajes por mes (WhatsApp Egresos) generado para task_id.
    El usuario debe tener permiso de reporte centro de contacto.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_whatsapp_mensajes_por_mes_egresos(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)


class DescargarCSVAgentsActivityV2ListadoView(View):
    """
    GET: redirige al archivo CSV de agents-activity-v2/Listado generado para task_id.
    """
    def get(self, request, *args, **kwargs):
        task_id = kwargs.get('task_id', '').strip()
        if not task_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(_('Falta task_id'))
        url = obtener_url_descarga_agents_activity_v2_listado(task_id)
        if url is None:
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound(
                _('El archivo no existe o aún no ha sido generado.')
            )
        return redirect(url)
