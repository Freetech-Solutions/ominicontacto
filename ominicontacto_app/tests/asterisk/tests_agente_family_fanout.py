# -*- coding: utf-8 -*-
"""Tests de preservación de fan-out / merge in-place en AgenteFamily (R1)."""
from __future__ import unicode_literals

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from ominicontacto_app.services.asterisk.redis_database import AgenteFamily


class AgenteFamilyFanoutPreserveTest(SimpleTestCase):

    def _agente(self, agent_id=7):
        agente = MagicMock()
        agente.id = agent_id
        agente.sip_extension = 1007
        agente.voicebot = False
        agente.user.get_full_name.return_value = 'Agent Seven'
        return agente

    def _hset_mappings(self, redis_conn):
        mappings = []
        for call in redis_conn.hset.call_args_list:
            args, kwargs = call
            if 'mapping' in kwargs:
                mappings.append(kwargs['mapping'])
            elif len(args) >= 2 and isinstance(args[1], dict):
                mappings.append(args[1])
        return mappings

    def test_regenerar_family_merge_sin_delete_preserva_fanout_y_status(self):
        """R1: preservar_status solo actualiza identidad; no DELETE."""
        redis_conn = MagicMock()
        family = 'OML:AGENT:7'
        hash_state = {
            'NAME': 'Old',
            'SIP': '1007',
            'STATUS': 'ONCALL',
            'TIMESTAMP': '100',
            'CALLID': 'call-99',
            'STREAMS': 'supervisor_1_agentes',
            'CAMPANAS': "['Camp A']",
            'GROUP': 'G1',
        }

        def hgetall(key):
            return dict(hash_state)

        def hset(key, mapping=None, **kwargs):
            mapping = mapping or kwargs.get('mapping') or {}
            hash_state.update(mapping)

        def hdel(key, *fields):
            for field in fields:
                hash_state.pop(field, None)

        redis_conn.hgetall.side_effect = hgetall
        redis_conn.hset.side_effect = hset
        redis_conn.hdel.side_effect = hdel

        family_svc = AgenteFamily(redis_connection=redis_conn)
        with patch.object(
            family_svc, '_publish_agent_after_regenerar'
        ) as publish_mock:
            family_svc.regenerar_family(self._agente(7), preservar_status=True)

        redis_conn.delete.assert_not_called()
        self.assertEqual(hash_state['NAME'], 'Agent Seven')
        self.assertEqual(hash_state['STATUS'], 'ONCALL')
        self.assertEqual(hash_state['CALLID'], 'call-99')
        self.assertEqual(hash_state['STREAMS'], 'supervisor_1_agentes')
        self.assertEqual(hash_state['CAMPANAS'], "['Camp A']")
        self.assertEqual(hash_state['GROUP'], 'G1')
        # No debe haber escrito STATUS en el mapping de identidad
        mappings = self._hset_mappings(redis_conn)
        self.assertTrue(all('STATUS' not in m for m in mappings))
        publish_mock.assert_called_once()
        preserved = publish_mock.call_args[0][2]
        self.assertEqual(preserved.get('STREAMS'), 'supervisor_1_agentes')

    def test_regenerar_family_sin_preservar_limpia_runtime_no_fanout(self):
        redis_conn = MagicMock()
        hash_state = {
            'NAME': 'Old',
            'STATUS': 'ONCALL',
            'CALLID': 'call-1',
            'CAMPAIGN': '9',
            'STREAMS': 'supervisor_1_agentes',
            'GROUP': 'G1',
        }

        def hgetall(key):
            return dict(hash_state)

        def hset(key, mapping=None, **kwargs):
            mapping = mapping or kwargs.get('mapping') or {}
            hash_state.update(mapping)

        def hdel(key, *fields):
            for field in fields:
                hash_state.pop(field, None)

        redis_conn.hgetall.side_effect = hgetall
        redis_conn.hset.side_effect = hset
        redis_conn.hdel.side_effect = hdel

        family_svc = AgenteFamily(redis_connection=redis_conn)
        with patch.object(family_svc, '_publish_agent_after_regenerar'):
            family_svc.regenerar_family(self._agente(3))

        redis_conn.delete.assert_not_called()
        self.assertEqual(hash_state['STATUS'], '')
        self.assertNotIn('CALLID', hash_state)
        self.assertNotIn('CAMPAIGN', hash_state)
        self.assertEqual(hash_state['STREAMS'], 'supervisor_1_agentes')
        self.assertEqual(hash_state['GROUP'], 'G1')

    def test_regenerar_family_sin_fanout_previo(self):
        redis_conn = MagicMock()
        hash_state = {'NAME': 'Old', 'STATUS': 'READY'}

        def hgetall(key):
            return dict(hash_state)

        def hset(key, mapping=None, **kwargs):
            mapping = mapping or kwargs.get('mapping') or {}
            hash_state.update(mapping)

        redis_conn.hgetall.side_effect = hgetall
        redis_conn.hset.side_effect = hset

        family_svc = AgenteFamily(redis_connection=redis_conn)
        with patch.object(family_svc, '_publish_agent_after_regenerar') as publish_mock:
            family_svc.regenerar_family(self._agente(3))

        redis_conn.delete.assert_not_called()
        preserved = publish_mock.call_args[0][2]
        self.assertEqual(preserved, {})

    def test_regenerar_families_merge_y_borra_huerfanos(self):
        redis_conn = MagicMock()
        store = {
            'OML:AGENT:7': {
                'STREAMS': 'supervisor_2_agentes',
                'GROUP': 'G2',
                'STATUS': 'READY',
                'NAME': 'x',
            },
            'OML:AGENT:99': {
                'STREAMS': 'orphan',
                'STATUS': 'OFFLINE',
            },
        }

        def hgetall(key):
            return dict(store.get(key, {}))

        def hset(key, mapping=None, **kwargs):
            mapping = mapping or kwargs.get('mapping') or {}
            store.setdefault(key, {}).update(mapping)

        def hdel(key, *fields):
            for field in fields:
                store.get(key, {}).pop(field, None)

        def delete(key):
            store.pop(key, None)

        redis_conn.scan_iter.return_value = list(store.keys())
        redis_conn.hgetall.side_effect = hgetall
        redis_conn.hset.side_effect = hset
        redis_conn.hdel.side_effect = hdel
        redis_conn.delete.side_effect = delete

        agente = self._agente(7)
        family_svc = AgenteFamily(redis_connection=redis_conn)
        with patch.object(family_svc, '_obtener_todos', return_value=[agente]):
            with patch.object(
                family_svc, '_publish_agent_after_regenerar'
            ) as publish_mock:
                family_svc.regenerar_families()

        self.assertNotIn('OML:AGENT:99', store)
        self.assertEqual(store['OML:AGENT:7']['STREAMS'], 'supervisor_2_agentes')
        self.assertEqual(store['OML:AGENT:7']['GROUP'], 'G2')
        self.assertEqual(store['OML:AGENT:7']['NAME'], 'Agent Seven')
        self.assertEqual(store['OML:AGENT:7']['STATUS'], '')
        publish_mock.assert_called()
        # No wipe del árbol activo
        self.assertNotEqual(
            [c[0][0] for c in redis_conn.delete.call_args_list if c[0]],
            ['OML:AGENT:7'],
        )
        deleted = [c[0][0] for c in redis_conn.delete.call_args_list]
        self.assertIn('OML:AGENT:99', deleted)
        self.assertNotIn('OML:AGENT:7', deleted)
