from django.views.generic import UpdateView
from django.views.generic.edit import ModelFormMixin
from django.core.urlresolvers import reverse
import random

import qcm.models
import qcm.forms


class DisplayQCMView(UpdateView):
    template_name = "qcm/display.html"
    slug_url_kwarg = 'year'
    pk_url_kwarg = 'year'
    context_object_name = 'qcm'
    form_class = qcm.forms.QcmForm
    model = qcm.models.Qcm

    @property
    def year(self):
        return self.kwargs[self.pk_url_kwarg]

    @property
    def is_editable(self):
        return self.request.user.is_authenticated() and self.object.event.is_active

    def get_success_url(self):
        return reverse('qcm:display', args=[self.year])

    def get_object(self, queryset=None):
        return ((self.get_queryset() if queryset is None else queryset)
                .get(event__edition__year=self.year))

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.event.is_finished:
            # just display the form so we can show right/wrong answers
            return self.form_invalid(self.get_form())
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        if not self.is_editable:
            return super(ModelFormMixin, self).form_valid(form)
        return super().form_valid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['contestant'] = self.request.current_contestant
        if self.request.user.is_authenticated():
            ordering_seed = self.request.user.pk
        else:
            try:
                ordering_seed = self.request.session['ordering_seed']
            except KeyError:
                ordering_seed = self.request.session['ordering_seed'] = random.random()
        kwargs['ordering_seed'] = ordering_seed
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['editable'] = self.is_editable
        context['correction'] = self.object.event.is_finished and self.request.method == 'POST'
        return context
