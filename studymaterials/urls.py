#studymaterials/urls.py


from django.urls import path
from . import views

urlpatterns = [
    # Study Weeks Endpoints
    path('weeks/', views.week_list, name='week_list'),
    path('weeks/create/', views.week_create, name='week_create'),
    path('weeks/<int:pk>/', views.week_detail, name='week_detail'),

    # Study Materials Endpoints
    path('materials/', views.material_list, name='material_list'),
    path('materials/create/', views.material_create, name='material_create'),
    path('materials/<int:pk>/', views.material_detail, name='material_detail'),
]