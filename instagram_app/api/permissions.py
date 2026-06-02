from django.utils.translation import ugettext as _

from api_app.views.permissions import TienePermisoOML


class TienePermisoCanalInstagramAgente(TienePermisoOML):
    message = _('No tiene permiso para usar la canalidad Instagram.')

    def has_permission(self, request, view):
        if not super(TienePermisoCanalInstagramAgente, self).has_permission(request, view):
            return False

        if not request.user.is_agente:
            return True

        try:
            agente = request.user.get_agente_profile()
        except Exception:
            return False

        return bool(getattr(agente.grupo, 'instagram_habilitado', False))
