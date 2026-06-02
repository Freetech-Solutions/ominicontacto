from ominicontacto_app.services.redis.redis_streams import RedisStreams
from instagram_app.models import CuentaInstagram


NOMBRE_STREAM = 'instagram_enabled_accounts'


class StreamDeCuentasInstagram(object):

    def notificar_nueva_cuenta(self, account):
        RedisStreams().write_stream(NOMBRE_STREAM, account.id)

    def notificar_cuenta_eliminada(self, account):
        RedisStreams().write_stream(NOMBRE_STREAM, account.id)

    def regenerar_stream(self):
        stream_manager = RedisStreams()
        stream_manager.flush(NOMBRE_STREAM)
        for account in CuentaInstagram.objects_default.all():
            if account.is_active:
                self.notificar_nueva_cuenta(account)
            else:
                self.notificar_cuenta_eliminada(account)
