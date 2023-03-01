from django.conf import settings
from rest_framework.routers import DefaultRouter, SimpleRouter

from sociallib.users.api.views import UserViewSet
from sociallib.chats.api.views import ConversationViewSet, MessageViewSet


if settings.DEBUG:
    router = DefaultRouter()
else:
    router = SimpleRouter()

router.register("users", UserViewSet)
router.register("conversations", ConversationViewSet)
router.register("messages", MessageViewSet)

app_name = "api"
urlpatterns = router.urls
