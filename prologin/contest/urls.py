from django.conf.urls import url
import contest.views


urlpatterns = [
    url(r'^(?P<year>[0-9]{4})/qualification', contest.views.QualificationSummary.as_view(), name='qualification_summary'),
]