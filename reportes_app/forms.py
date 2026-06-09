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
from __future__ import unicode_literals

import json

from django.utils.translation import gettext_lazy as _
from django import forms

from ominicontacto_app.models import Campana
from ominicontacto_app.utiles import convert_fecha_datetime


EMPTY_CHOICE = ('', '---------')


class ReporteAgentesForm(forms.Form):
    """
    El form para reporte con fecha
    """
    fecha = forms.CharField(widget=forms.TextInput(
        attrs={'class': 'form-control'}))
    agente = forms.MultipleChoiceField(required=False, choices=())
    grupo_agente = forms.ChoiceField(required=False, choices=(), widget=forms.Select(
        attrs={'class': 'form-control'}))
    todos_agentes = forms.BooleanField(required=False)

    def __init__(self, agentes_asociados, grupos_asociados, *args, **kwargs):
        super(ReporteAgentesForm, self).__init__(*args, **kwargs)

        agente_choice = [(agente.pk, agente.user.get_full_name())
                         for agente in agentes_asociados]
        self.fields['agente'].choices = agente_choice
        grupo_choice = [(grupo.id, grupo.nombre)
                        for grupo in grupos_asociados]
        grupo_choice.insert(0, EMPTY_CHOICE)
        self.fields['grupo_agente'].choices = grupo_choice

    def clean(self):
        agentes = self.cleaned_data.get('agente')
        todos_agentes = self.cleaned_data.get('todos_agentes')
        grupos = self.cleaned_data.get('grupo_agente')
        if not agentes and not todos_agentes and not grupos:
            msg = _('Es necesario elegir un agente mínimo')
            raise forms.ValidationError(msg)
        return super(ReporteAgentesForm, self).clean()


class ReporteLlamadasForm(forms.Form):
    """
    El form para reporte de llamadas
    """
    fecha = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}))
    finalizadas = forms.BooleanField(required=False, label=_('Incluir campañas finalizadas'))

    def clean_fecha(self):
        fecha = self.cleaned_data.get('fecha')
        try:
            fecha_desde, fecha_hasta = fecha.split('-')
            fecha_desde = convert_fecha_datetime(fecha_desde)
            fecha_hasta = convert_fecha_datetime(fecha_hasta, final_dia=True)
        except ValueError:
            raise forms.ValidationError(_('Formato inválido'))
        self.desde = fecha_desde
        self.hasta = fecha_hasta
        return fecha


class EstadisticasJSONForm(forms.Form):
    estadisticas = forms.CharField()

    def clean_estadisticas(self):
        estadisticas = self.cleaned_data.get('estadisticas')
        try:
            json_data = json.loads(estadisticas)
        except ValueError:
            raise forms.ValidationError(_(u'Formato JSON invalido'))
        return json_data


TIPO_REPORTE_CHOICES = (
    ('llamadas_por_tipo', ''),
    ('llamadas_por_campana', ''),
    ('tipos_de_llamada_manual', ''),
    ('tipos_de_llamada_dialer', ''),
    ('tipos_de_llamada_entrante', ''),
    ('tipos_de_llamada_preview', ''),
)


class ExportarReporteLlamadasForm(EstadisticasJSONForm):
    tipo_reporte = forms.ChoiceField(choices=TIPO_REPORTE_CHOICES, required=True)


class ReporteCentroContactoForm(forms.Form):
    """
    Formulario para el reporte de Centro de Contacto.
    Permite elegir cualquier tipo de campaña (Manual, Preview, Dialer, Entrante).
    """
    TODAS_LAS_CAMPANAS_VALUE = '__all__'
    TODOS_LOS_GRUPOS_VALUE = '__all_groups__'
    TODOS_LOS_AGENTES_VALUE = '__all_agents__'

    fecha = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label=_('Rango de fechas')
    )
    campana = forms.MultipleChoiceField(
        required=False,
        choices=(),
        widget=forms.SelectMultiple(attrs={'class': 'form-control'}),
        label=_('Campañas')
    )
    incluir_finalizadas = forms.BooleanField(
        required=False,
        initial=False,
        label=_('Incluir campañas finalizadas')
    )
    grupo_agente = forms.MultipleChoiceField(
        required=False,
        choices=(),
        widget=forms.SelectMultiple(attrs={'class': 'form-control'}),
        label=_('Grupo de agentes')
    )
    agente = forms.MultipleChoiceField(
        required=False,
        choices=(),
        widget=forms.SelectMultiple(attrs={'class': 'form-control'}),
        label=_('Agentes')
    )
    contacto_id = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': _('Ej: 12345')}),
        label=_('ID de contacto')
    )
    address = forms.CharField(
        required=False,
        strip=True,
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': _('Ej: +54911..., user@dominio.com, usuario_fb')
            }
        ),
        label=_('Telefono / Address / Username')
    )
    callid = forms.CharField(
        required=False,
        strip=True,
        max_length=64,
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': _('Ej: 1234567890.123'),
            }
        ),
        label=_('Call ID'),
    )
    hora_desde = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
        label=_('Hora desde')
    )
    hora_hasta = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
        label=_('Hora hasta')
    )
    duracion_agente_min = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(
            attrs={'class': 'form-control', 'placeholder': _('Ej: 60')}
        ),
        label=_('Duracion agente')
    )
    duracion_bot_min = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(
            attrs={'class': 'form-control', 'placeholder': _('Ej: 60')}
        ),
        label=_('Duracion bot')
    )

    def __init__(self, campanas_asignadas=None, grupos_agentes=None, agentes_asignados=None,
                 *args, **kwargs):
        super(ReporteCentroContactoForm, self).__init__(*args, **kwargs)

        if campanas_asignadas is None:
            campanas_asignadas = []
        if grupos_agentes is None:
            grupos_agentes = []
        if agentes_asignados is None:
            agentes_asignados = []

        campana_choices = [
            (
                str(c.id),
                '{0}{1}'.format(
                    c.nombre,
                    _(' (Finalizada)') if c.estado == Campana.ESTADO_FINALIZADA else ''
                )
            )
            for c in campanas_asignadas
        ]
        campana_choices.insert(0, (self.TODAS_LAS_CAMPANAS_VALUE, _('Todas')))
        self.fields['campana'].choices = campana_choices
        finalized_ids = [
            str(c.id) for c in campanas_asignadas if c.estado == Campana.ESTADO_FINALIZADA
        ]
        self.fields['campana'].widget.attrs.update({
            'data-finalized-ids': ','.join(finalized_ids),
            'data-all-campaign-value': self.TODAS_LAS_CAMPANAS_VALUE,
            'data-placeholder': _('Seleccione campañas'),
        })

        grupo_choices = [(str(grupo.id), grupo.nombre) for grupo in grupos_agentes]
        grupo_choices.insert(
            0, (self.TODOS_LOS_GRUPOS_VALUE, _('Todos'))
        )
        self.fields['grupo_agente'].choices = grupo_choices
        self.fields['grupo_agente'].widget.attrs.update({
            'data-all-groups-value': self.TODOS_LOS_GRUPOS_VALUE,
            'data-placeholder': _('Seleccione grupos de agentes'),
        })

        agente_choices = [
            (
                str(agente.id),
                agente.user.get_full_name() or agente.user.username
            )
            for agente in agentes_asignados
        ]
        agente_choices.insert(
            0, (self.TODOS_LOS_AGENTES_VALUE, _('Todos'))
        )
        self.fields['agente'].choices = agente_choices
        self.fields['agente'].widget.attrs.update({
            'data-all-agents-value': self.TODOS_LOS_AGENTES_VALUE,
            'data-placeholder': _('Seleccione agentes'),
        })

        if not self.is_bound:
            self.initial.setdefault('grupo_agente', [self.TODOS_LOS_GRUPOS_VALUE])
            self.fields['grupo_agente'].initial = [self.TODOS_LOS_GRUPOS_VALUE]
            self.initial.setdefault('agente', [self.TODOS_LOS_AGENTES_VALUE])
            self.fields['agente'].initial = [self.TODOS_LOS_AGENTES_VALUE]

    def clean_fecha(self):
        fecha = self.cleaned_data.get('fecha')
        if not fecha or not fecha.strip():
            raise forms.ValidationError(_('Indique el rango de fechas (desde-hasta).'))
        fecha = fecha.strip()
        try:
            partes = fecha.split('-', 1)
            if len(partes) != 2:
                raise forms.ValidationError(_('Formato inválido. Use: dd/mm/aaaa-dd/mm/aaaa'))
            fecha_desde = convert_fecha_datetime(partes[0].strip())
            fecha_hasta = convert_fecha_datetime(partes[1].strip(), final_dia=True)
        except (ValueError, IndexError):
            raise forms.ValidationError(_('Formato inválido. Use: dd/mm/aaaa-dd/mm/aaaa'))
        self.desde = fecha_desde
        self.hasta = fecha_hasta
        return fecha

    def clean(self):
        cleaned_data = super(ReporteCentroContactoForm, self).clean()
        campanas = cleaned_data.get('campana') or []
        incluir_finalizadas = cleaned_data.get('incluir_finalizadas', False)
        grupos = cleaned_data.get('grupo_agente') or []
        agentes = cleaned_data.get('agente') or []
        address = cleaned_data.get('address')

        if self.TODAS_LAS_CAMPANAS_VALUE in campanas and len(campanas) > 1:
            campanas = [self.TODAS_LAS_CAMPANAS_VALUE]

        finalized_ids_raw = self.fields['campana'].widget.attrs.get('data-finalized-ids', '')
        finalized_ids = set([cid for cid in finalized_ids_raw.split(',') if cid])
        if not incluir_finalizadas:
            selected_finalized = [cid for cid in campanas if cid in finalized_ids]
            if selected_finalized:
                self.add_error(
                    'campana',
                    _('Para seleccionar campañas finalizadas active "Incluir campañas finalizadas".')
                )

        if not grupos:
            grupos = [self.TODOS_LOS_GRUPOS_VALUE]
        elif self.TODOS_LOS_GRUPOS_VALUE in grupos and len(grupos) > 1:
            grupos = [self.TODOS_LOS_GRUPOS_VALUE]

        grupos_validos = set([
            str(choice_id)
            for choice_id, _ in self.fields['grupo_agente'].choices
            if choice_id != self.TODOS_LOS_GRUPOS_VALUE
        ])
        grupos_invalidos = [
            group_id for group_id in grupos
            if group_id != self.TODOS_LOS_GRUPOS_VALUE and group_id not in grupos_validos
        ]
        if grupos_invalidos:
            self.add_error('grupo_agente', _('Grupo de agentes inválido.'))

        if not agentes:
            agentes = [self.TODOS_LOS_AGENTES_VALUE]
        elif self.TODOS_LOS_AGENTES_VALUE in agentes and len(agentes) > 1:
            agentes = [self.TODOS_LOS_AGENTES_VALUE]

        agentes_validos = set([
            str(choice_id)
            for choice_id, _ in self.fields['agente'].choices
            if choice_id != self.TODOS_LOS_AGENTES_VALUE
        ])
        agentes_invalidos = [
            agent_id for agent_id in agentes
            if agent_id != self.TODOS_LOS_AGENTES_VALUE and agent_id not in agentes_validos
        ]
        if agentes_invalidos:
            self.add_error('agente', _('Agente inválido.'))

        if address is not None:
            address = address.strip()

        cleaned_data['campana'] = campanas
        cleaned_data['grupo_agente'] = grupos
        cleaned_data['agente'] = agentes
        cleaned_data['address'] = address or None
        return cleaned_data


class ReporteNivelServicioForm(forms.Form):
    """
    Formulario para el reporte de Nivel de Servicio (Service Level)
    """
    fecha = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label=_('Rango de fechas')
    )
    campana = forms.ChoiceField(
        required=False,
        choices=(),
        widget=forms.Select(attrs={'class': 'form-control'}),
        label=_('Campaña')
    )
    tiempo_objetivo = forms.IntegerField(
        required=False,
        initial=20,
        min_value=1,
        max_value=300,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        label=_('Tiempo objetivo (segundos)'),
        help_text=_('Tiempo máximo de espera en cola para considerar cumplimiento del objetivo (default: 20s)')
    )

    def __init__(self, campanas_asignadas=None, *args, **kwargs):
        super(ReporteNivelServicioForm, self).__init__(*args, **kwargs)
        
        if campanas_asignadas is None:
            campanas_asignadas = []
        
        # Filtrar campañas entrantes y Dialer
        from ominicontacto_app.models import Campana
        campanas_filtradas = [c for c in campanas_asignadas 
                              if c.type in [Campana.TYPE_ENTRANTE, Campana.TYPE_DIALER]]
        
        campana_choices = [(c.id, c.nombre) for c in campanas_filtradas]
        campana_choices.insert(0, ('', _('Todas las campañas (entrantes y Dialer)')))
        self.fields['campana'].choices = campana_choices

    def clean_fecha(self):
        fecha = self.cleaned_data.get('fecha')
        if not fecha or not fecha.strip():
            raise forms.ValidationError(_('Indique el rango de fechas (desde-hasta).'))
        fecha = fecha.strip()
        try:
            partes = fecha.split('-', 1)
            if len(partes) != 2:
                raise forms.ValidationError(_('Formato inválido. Use: dd/mm/aaaa-dd/mm/aaaa'))
            fecha_desde = convert_fecha_datetime(partes[0].strip())
            fecha_hasta = convert_fecha_datetime(partes[1].strip(), final_dia=True)
        except (ValueError, IndexError):
            raise forms.ValidationError(_('Formato inválido. Use: dd/mm/aaaa-dd/mm/aaaa'))
        self.desde = fecha_desde
        self.hasta = fecha_hasta
        return fecha
