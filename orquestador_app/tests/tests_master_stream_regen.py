# -*- coding: utf-8 -*-
"""Master-stream regenerate must not flush when already seeded."""
from __future__ import unicode_literals

import unittest
from unittest.mock import MagicMock, patch


class MasterStreamRegenTests(unittest.TestCase):

    def test_whatsapp_regen_skips_when_stream_nonempty(self):
        from whatsapp_app.services.redis.linea import (
            NOMBRE_STREAM_LINEAS,
            StreamDeLineas,
        )

        conn = MagicMock()
        conn.xlen.return_value = 3
        streams = MagicMock()
        streams.connection = conn

        with patch(
            'whatsapp_app.services.redis.linea.RedisStreams',
            return_value=streams,
        ):
            result = StreamDeLineas().regenerar_stream()

        self.assertFalse(result)
        conn.xlen.assert_called_once_with(NOMBRE_STREAM_LINEAS)
        streams.flush.assert_not_called()
        streams.write_stream.assert_not_called()

    def test_facebook_regen_skips_when_stream_nonempty(self):
        from facebook_meta_app.services.redis.page import (
            NOMBRE_STREAM,
            StreamDePaginas,
        )

        conn = MagicMock()
        conn.xlen.return_value = 2
        streams = MagicMock()
        streams.connection = conn

        with patch(
            'facebook_meta_app.services.redis.page.RedisStreams',
            return_value=streams,
        ):
            result = StreamDePaginas().regenerar_stream()

        self.assertFalse(result)
        conn.xlen.assert_called_once_with(NOMBRE_STREAM)
        streams.flush.assert_not_called()


if __name__ == '__main__':
    unittest.main()
