# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions

# This file is part of OMniLeads

from unittest.mock import MagicMock, patch

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase

from ominicontacto_app.services.asterisk.asterisk_ami import AMIManagerConnector
from ominicontacto_app.services.asterisk.supervisor_activity import SupervisorActivityAmiManager
from ominicontacto_app.tests.factories import AgenteProfileFactory, SupervisorProfileFactory


class AMIManagerConnectorNoDirectConnectionTest(TestCase):
    """Django no debe conectar directamente a Asterisk."""

    def test_connect_raises_improperly_configured(self):
        connector = AMIManagerConnector()
        with self.assertRaises(ImproperlyConfigured) as ctx:
            connector.connect()
        self.assertIn("Django no debe conectar directamente a Asterisk", str(ctx.exception))


class SupervisorActivityTakeCallTest(TestCase):
    """Tests para la acción CHANTAKECALL (tomar llamada) vía Redis/ARI."""

    def setUp(self):
        self.supervisor = SupervisorProfileFactory()
        self.agente_profile = AgenteProfileFactory()

    @patch('ominicontacto_app.services.asterisk.supervisor_activity.create_redis_connection')
    def test_chantakecall_publishes_take_call_to_redis(self, mock_create_redis):
        """CHANTAKECALL debe publicar en Redis action take_call con callid y supervisor_sip."""
        call_id = "call-123"
        node_id = "node-1"
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {
            b"CALLID": call_id.encode("utf-8"),
            b"NODE_ID": node_id.encode("utf-8"),
        }
        mock_create_redis.return_value = mock_redis

        servicio = SupervisorActivityAmiManager()
        error = servicio.ejecutar_accion_sobre_agente(
            self.supervisor, self.agente_profile, "CHANTAKECALL"
        )

        self.assertIsNone(error)
        mock_redis.publish.assert_called_once()
        channel = mock_redis.publish.call_args[0][0]
        payload_str = mock_redis.publish.call_args[0][1]
        self.assertEqual(channel, "acd:commands:{}".format(node_id))
        import json
        payload = json.loads(payload_str)
        self.assertEqual(payload["action"], "take_call")
        self.assertEqual(payload["callid"], call_id)
        self.assertEqual(payload["supervisor_sip"], str(self.supervisor.sip_extension))

    @patch('ominicontacto_app.services.asterisk.supervisor_activity.create_redis_connection')
    def test_chantakecall_returns_error_when_agent_not_in_call(self, mock_create_redis):
        """CHANTAKECALL sin CALLID en Redis debe devolver mensaje de error."""
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {}  # Sin datos de llamada
        mock_create_redis.return_value = mock_redis

        servicio = SupervisorActivityAmiManager()
        error = servicio.ejecutar_accion_sobre_agente(
            self.supervisor, self.agente_profile, "CHANTAKECALL"
        )

        self.assertIsNotNone(error)
        mock_redis.publish.assert_not_called()
