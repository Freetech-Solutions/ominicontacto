# -*- coding: utf-8 -*-
# Copyright (C) 2026 Freetech Solutions
#
# This file is part of OMniLeads
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3, as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see http://www.gnu.org/licenses/.
#
from __future__ import unicode_literals

from django.urls import reverse
from rest_framework import status

from email_app import models
from ominicontacto_app.models import User
from ominicontacto_app.tests.factories import CampanaFactory
from ominicontacto_app.tests.utiles import OMLBaseTest, PASSWORD


class AccountABMTest(OMLBaseTest):
    """ABM (alta/baja/modificación) de cuentas de correo (email_app)."""

    def setUp(self):
        super(AccountABMTest, self).setUp()
        self.admin = self.crear_supervisor_profile(rol=User.ADMINISTRADOR)
        self.client.login(username=self.admin.user.username, password=PASSWORD)

    def _payload(self, name):
        return {
            "name": name,
            "active": True,
            "inbound": {
                "protocol": "imap+ssl",
                "host": "imap.example.com",
                "port": 993,
                "auth_type": "basic",
                "username": "user@example.com",
                "password": "secret-inbound",
                "fetch_mode": "poll",
                "idle_duration": 300,
                "poll_interval": 300,
                "mailbox": "INBOX",
                "since": "",
                "ssl_check_hostname": True,
            },
            "outbound": {
                "protocol": "smtp+tls",
                "host": "smtp.example.com",
                "port": 587,
                "auth_type": "basic",
                "username": "user@example.com",
                "password": "secret-outbound",
                "from_addr": "user@example.com",
            },
        }

    def _create_account(self, name):
        payload = self._payload(name)
        settings = {"inbound": payload["inbound"], "outbound": payload["outbound"]}
        return models.Account.objects.create(name=name, active=True, settings=settings)

    # --- Alta (create) -----------------------------------------------------

    def test_account_create(self):
        url = reverse("email:api:v1:account-list")
        response = self.client.post(
            url, self._payload("alta-cuenta"), content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(models.Account.objects.filter(name="alta-cuenta").exists())

    def test_account_create_rejects_xoauth2(self):
        """OAuth2 (xoauth2) no está implementado: el alta debe rechazarse con
        400 en validación, en lugar de crear una cuenta que luego rompe el
        servicio de sync con 'Unhandled auth_type'."""
        url = reverse("email:api:v1:account-list")
        payload = self._payload("xoauth2-cuenta")
        payload["inbound"]["auth_type"] = "xoauth2"
        response = self.client.post(url, payload, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(models.Account.objects.filter(name="xoauth2-cuenta").exists())

    # --- Modificación (update) ---------------------------------------------

    def test_account_update(self):
        account = self._create_account("nombre-viejo")
        url = reverse("email:api:v1:account-detail", args=[account.pk])
        response = self.client.put(
            url, self._payload("nombre-nuevo"), content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        account.refresh_from_db()
        self.assertEqual(account.name, "nombre-nuevo")

    # --- Baja (delete) -----------------------------------------------------

    def test_account_delete(self):
        account = self._create_account("a-borrar")
        url = reverse("email:api:v1:account-detail", args=[account.pk])
        response = self.client.delete(url, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(models.Account.objects.filter(pk=account.pk).exists())

    def test_account_delete_in_use_returns_conflict(self):
        """Borrar una cuenta usada por una campaña responde 409 con leyenda
        amigable que nombra la campaña, en lugar del 500 por ProtectedError."""
        account = self._create_account("en-uso")
        campana = CampanaFactory.create()
        models.CampaignAccount.objects.create(campaign=campana, account=account)

        url = reverse("email:api:v1:account-detail", args=[account.pk])
        response = self.client.delete(url, content_type="application/json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn(campana.nombre, response.json()["detail"])
        # La cuenta NO debe haber sido eliminada.
        self.assertTrue(models.Account.objects.filter(pk=account.pk).exists())

    # --- Permisos ----------------------------------------------------------

    def test_account_requires_authentication(self):
        self.client.logout()
        account = self._create_account("sin-auth")
        list_url = reverse("email:api:v1:account-list")
        detail_url = reverse("email:api:v1:account-detail", args=[account.pk])
        self.assertEqual(self.client.get(list_url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client.post(list_url).status_code, status.HTTP_403_FORBIDDEN
        )
        self.assertEqual(
            self.client.delete(detail_url).status_code, status.HTTP_403_FORBIDDEN
        )
