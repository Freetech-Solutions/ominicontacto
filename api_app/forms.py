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

from django.utils.translation import gettext_lazy as _
from django import forms
from django.forms.models import ModelChoiceField

from ominicontacto_app.models import Campana, Contacto, AgenteEnSistemaExterno


class Click2CallParametersBaseForm(forms.Form):
    phone = forms.CharField(max_length=128)

    def __init__(self, agente, *args, **kwargs):
        super(Click2CallParametersBaseForm, self).__init__(*args, **kwargs)
        self.agente = agente

    def clean_idCampaign(self):
        campana = self.cleaned_data.get('idCampaign', None)
        if campana and not campana.queue_campana.members.filter(id=self.agente.id).exists():
            raise forms.ValidationError(_('El agente no participa en la campaña.'))
        return campana

    def get_campana(self):
        return self.cleaned_data.get('idCampaign')

    def get_contacto_id(self):
        raise NotImplementedError()


class Click2CallOMLParametersForm(Click2CallParametersBaseForm):
    idCampaign = ModelChoiceField(queryset=Campana.objects.obtener_activas())
    idContact = ModelChoiceField(queryset=Contacto.objects.all(), required=False)

    def clean_idContact(self):
        campana = self.cleaned_data.get('idCampaign', None)
        contacto = self.cleaned_data.get('idContact', None)
        if campana and contacto:
            if contacto.bd_contacto == campana.bd_contacto:
                self._contacto = contacto
                return contacto
            raise forms.ValidationError(_('El contacto no corresponde a la campaña.'))

    def get_contacto_id(self):
        contacto = self.cleaned_data.get('idContact', '')
        if contacto:
            return contacto.id
        return ''


class Click2CallExternalSiteParametersForm(Click2CallParametersBaseForm):
    idCampaign = ModelChoiceField(queryset=Campana.objects.obtener_activas(),
                                  to_field_name='id_externo')
    # No puede ser ModelChoiceField.
    idContact = forms.CharField(max_length=128, required=False)

    def __init__(self, agente, sistema_externo, *args, **kwargs):
        super(Click2CallExternalSiteParametersForm, self).__init__(agente, *args, **kwargs)
        self.sistema_externo = sistema_externo
        self.fields['idCampaign'].queryset = Campana.objects.filter(sistema_externo=sistema_externo)
        self._contacto = None

    def clean(self):
        cleaned_data = super(Click2CallExternalSiteParametersForm, self).clean()
        if not AgenteEnSistemaExterno.objects.filter(
                sistema_externo=self.sistema_externo, agente=self.agente).exists():
            raise forms.ValidationError(_('El agente no corresponde al sistema externo.'))
        return cleaned_data

    def clean_idContact(self):
        campana = self.cleaned_data.get('idCampaign', None)
        contacto = self.cleaned_data.get('idContact', None)
        if campana and contacto:
            try:
                contacto = campana.bd_contacto.contactos.get(id_externo=contacto)
                self._contacto = contacto
                return contacto
            except Contacto.DoesNotExist:
                self._contacto = None

    def get_contacto_id(self):
        if self._contacto is None:
            return ''
        return self._contacto.id
