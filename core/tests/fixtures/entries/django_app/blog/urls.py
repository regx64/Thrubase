from django.urls import path

from . import views
from .views import PostView

urlpatterns = [
    path("", views.index, name="index"),
    path("posts/", PostView.as_view(), name="posts"),
]
