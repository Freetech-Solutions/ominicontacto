from django.conf.urls import include
from django.contrib.auth.decorators import login_required
from django.urls import path

from instagram_app.api.urls import urlpatterns as api_urlpatterns
from instagram_app.views import InstagramAccountConfigurationView


urlpatterns = [
    path('connections/instagram/accounts/',
         login_required(InstagramAccountConfigurationView.as_view()),
         name='instagram_accounts_configuration'),
    path('api/v1/instagram/', include((api_urlpatterns, 'instagram_app'), namespace='instagram')),
]
