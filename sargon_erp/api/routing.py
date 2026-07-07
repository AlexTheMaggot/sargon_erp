from django.urls import path

from .consumers import OperationsConsumer


websocket_urlpatterns = [
    path('ws/operations/', OperationsConsumer.as_asgi()),
]
