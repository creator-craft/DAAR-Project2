from django.urls import path

from library import views

urlpatterns = [
    path("api/stats", views.stats),
    path("api/search", views.search),
]
