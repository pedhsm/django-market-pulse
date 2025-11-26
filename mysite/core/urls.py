from django.urls import path 
from . import views 

# OK!!
urlpatterns = [
    path('',views.index,name='index'),
]