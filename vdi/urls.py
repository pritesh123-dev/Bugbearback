from django.urls import path
from .views import CreateInstanceView, StopInstanceView, DeleteInstanceView, VdiListView, ConnectVDIView

urlpatterns = [
    path('create/', CreateInstanceView.as_view(), name='create_instance'),
    path('stop/', StopInstanceView.as_view(), name='stop_instance'),
    path('delete/', DeleteInstanceView.as_view(), name='delete_instance'),
    path('list/', VdiListView.as_view(), name='list_instance'),
    path('connect/<int:instance_id>', ConnectVDIView.as_view(), name='connect_instance'),

]
