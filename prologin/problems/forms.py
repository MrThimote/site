from django import forms
from django.conf import settings
from django.utils.translation import ugettext_lazy as _

from contest.models import Event
import contest.models
import problems.models
import prologin.languages
from prologin.utils import read_try_hard, sizeof_fmt


class SearchForm(forms.Form):
    query = forms.CharField(required=False,
                            widget=forms.TextInput(attrs={'placeholder': _("Problem name (optional)")}),
                            label=_("Query"))
    event_type = forms.ChoiceField(choices=[('', _("Any event type")),
                                            (Event.Type.qualification.name,
                                             Event.Type.label_for(Event.Type.qualification)),
                                            (Event.Type.semifinal.name,
                                             Event.Type.label_for(Event.Type.semifinal))],
                                   required=False,
                                   label=_("Event type"))
    difficulty_min = forms.IntegerField(min_value=0, max_value=settings.PROLOGIN_MAX_LEVEL_DIFFICULTY,
                                        initial=0,
                                        required=False,
                                        label=_("Minimum difficulty"))
    difficulty_max = forms.IntegerField(min_value=0, max_value=settings.PROLOGIN_MAX_LEVEL_DIFFICULTY,
                                        initial=settings.PROLOGIN_MAX_LEVEL_DIFFICULTY,
                                        required=False,
                                        label=_("Maximum difficulty"))
    solved = forms.ChoiceField(required=False, initial='', label=_("Solved"),
                               choices=[('', _("All problems")),
                                        ('solved', _("Problems I solved")),
                                        ('unsolved', _("Problems I did not solve"))])

    def clean_query(self):
        return self.cleaned_data['query'].lower().strip()

    def clean(self):
        cd = self.cleaned_data
        if (cd.get('difficulty_min') is not None and
                cd.get('difficulty_max') is not None and
                cd['difficulty_min'] > cd['difficulty_max']):
            cd['difficulty_min'], cd['difficulty_max'] = cd['difficulty_max'], cd['difficulty_min']
        return cd


class ProblemWidget(forms.MultiWidget):
    def __init__(self):
        # Code, language
        widgets = [forms.Textarea(), forms.Select()]
        super().__init__(widgets=widgets)

    def decompress(self, value):
        if value is None:
            return []
        return [value.code, value.language]


class ProblemField(forms.MultiValueField):
    widget = ProblemWidget

    def __init__(self, *args, **kwargs):
        fields = (
            forms.CharField(),
            forms.ChoiceField(choices=prologin.languages.Language.choices())
        )
        super().__init__(fields, *args, **kwargs)

    def compress(self, data_list):
        return data_list


class ProblemsForm(forms.ModelForm):
    class Meta:
        model = contest.models.Event
        fields = ()

    def __init__(self, *args, **kwargs):
        self.contestant = kwargs.pop('contestant', None)
        super().__init__(*args, **kwargs)

        problem_list = problems.models.Challenge.objects.filter(event=self.instance)
        if self.contestant:
            answers = {a.challenge.pk: a
                       for a in problems.models.Answer.objects.prefetch_related('challenge')
                                                      .filter(contestant=self.contestant,
                                                              challenge__event=self.instance)}

        for problem in problem_list:
            field_key = 'problem_%d' % problem.pk
            field = self.fields[field_key] = ProblemField()
            field.problem = problem
            if self.contestant:
                field.initial = answers.get(problem.pk)

    def save(self, commit=True):
        return self.instance


class CodeSubmissionForm(forms.ModelForm):
    sourcefile = forms.FileField(required=False)

    class Meta:
        model = problems.models.SubmissionCode
        fields = ('language', 'code', 'summary', 'sourcefile')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['code'].required = False

    def clean(self):
        if self.cleaned_data.get('sourcefile') and self.cleaned_data.get('code'):
            raise forms.ValidationError(_("You can provide either a source file or a source code, but not both."))
        if self.cleaned_data.get('sourcefile'):
            try:
                size = self.cleaned_data['sourcefile'].size
            except AttributeError:
                raise forms.ValidationError(_("Your client did not provide the content length of your source file."))
            if size > settings.PROBLEMS_UPLOAD_MAX_LENGTH:
                raise forms.ValidationError(_("The source file you uploaded is too large. "
                                              "Please keep it below %(size)s.") %
                                            {'size': sizeof_fmt(settings.PROBLEMS_UPLOAD_MAX_LENGTH)})
            try:
                self.cleaned_data['code'] = read_try_hard(self.cleaned_data['sourcefile'], size)
            except ValueError:
                raise forms.ValidationError(_("Please use the UTF-8 encoding when uploading a source file."))
            if '\x00' in self.cleaned_data['code']:
                raise forms.ValidationError(_("Source files cannot contain NUL (0x00) characters."))
            self.cleaned_data['sourcefile'] = None
        elif not self.cleaned_data.get('code'):
            raise forms.ValidationError(_("You need to provide either a source file or a source code."))
        return self.cleaned_data
