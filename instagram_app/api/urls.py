import instagram_app.api.v1.account_configuration
import instagram_app.api.v1.contact
import instagram_app.api.v1.conversation
import instagram_app.api.v1.templates
import instagram_app.api.v1.templates_instagram
import instagram_app.api.v1.transfer

from instagram_app.api import ViewSetRouter


router = ViewSetRouter(trailing_slash=False)

routes = (
    (r"account", instagram_app.api.v1.account_configuration.ViewSet),
    (r"campaigns", instagram_app.api.v1.account_configuration.CampaignViewSet),
    (r"schedules", instagram_app.api.v1.account_configuration.ScheduleViewSet),
    (r"chat", instagram_app.api.v1.conversation.ViewSet),
    (r"contact/(?P<campana_pk>[^/.]+)", instagram_app.api.v1.contact.ViewSet),
    (r"transfer", instagram_app.api.v1.transfer.ViewSet),
    (r"templates/(?P<campana_pk>[^/.]+)", instagram_app.api.v1.templates.ViewSet),
    (r"templates_instagram", instagram_app.api.v1.templates_instagram.ViewSet),
)

for prefix, viewset in routes:
    router.register(prefix, viewset)

urlpatterns = router.urls
