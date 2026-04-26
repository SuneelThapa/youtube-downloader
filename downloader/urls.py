from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('progress/<str:job_id>/', views.progress_view, name='progress'),
    path('download/<str:job_id>/', views.download_file, name='download_file'),
    path('debug/<str:job_id>/', views.debug_progress),
]