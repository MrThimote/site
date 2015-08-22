from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.views.generic import TemplateView, RedirectView, ListView, DetailView, CreateView
from django.views.generic.detail import BaseDetailView
from django.views.generic.edit import ModelFormMixin
import celery
import celery.exceptions

from contest.models import Event
from problems.forms import SearchForm, CodeSubmissionForm
from prologin.languages import Language
from problems.tasks import submit_problem_code
import problems.models


def get_challenge(kwargs):
    """
    Load a challenge from URL kwargs.
    """
    year = int(kwargs['year'])
    try:
        event_type = Event.Type[kwargs['type']]
    except KeyError:
        raise Http404()
    try:
        challenge = problems.models.Challenge.by_year_and_event_type(year, event_type)
        if not challenge.displayable:
            raise ObjectDoesNotExist
    except ObjectDoesNotExist:
        raise Http404()
    return year, event_type, challenge


def get_problem(kwargs):
    """
    Load a problem (and its challenge) from URL kwargs.
    """
    year, event_type, challenge = get_challenge(kwargs)
    try:
        problem = problems.models.Problem(challenge, kwargs['problem'])
    except ObjectDoesNotExist:
        raise Http404()
    return year, event_type, challenge, problem


def get_user_submissions(user, extra_filters=Q()):
    """
    Fetch all submissions for the given user, using extra filters if needed.
    """
    return (problems.models.Submission.objects
                           .filter(user=user)
                           .filter(extra_filters)
                           .prefetch_related('codes'))


class Index(TemplateView):
    """
    The problem index view. Displays a table of challenges grouped by year and the search form.
    """
    template_name = 'problems/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['challenges'] = [c for c in problems.models.Challenge.all() if c.displayable]
        context['search_form'] = SearchForm()
        return context


class Challenge(TemplateView):
    """
    The challenge index view. Displays the challenge statement and the list of
    all problems within a challenge along with the user score, if authenticated.
    """
    template_name = 'problems/challenge.html'
    # Event.Type name → (Event.Type, challenge prefix)
    event_category_mapping = {
        Event.Type.qualification.name: (Event.Type.qualification, 'qcm'),
        Event.Type.semifinal.name: (Event.Type.semifinal, 'demi'),
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        year, event_type, challenge = get_challenge(self.kwargs)
        challenge_score = 0
        challenge_done = 0

        context['challenge'] = challenge
        context['problems'] = sorted(challenge.problems, key=lambda p: p.difficulty)

        if self.request.user.is_authenticated():
            # To display user score on each problem
            submissions = get_user_submissions(self.request.user,
                                               extra_filters=Q(challenge=challenge.name))
            submissions = {sub.problem: sub for sub in submissions}
            for problem in context['problems']:
                submission = submissions.get(problem.name)
                # Monkey-patch the problem to add the submission object
                if submission:
                    problem.submission = submission
                    challenge_score += submission.score()
                    if submission.succeeded():
                        challenge_done += 1

        context['challenge_score'] = challenge_score
        context['challenge_done'] = challenge_done == len(challenge.problems)

        return context


class Problem(CreateView):
    """
    Displays a single problem with its statement, its constraints, its samples
    and if the user is authenticated, the code editor and her previous submissions.
    """
    form_class = CodeSubmissionForm
    model = problems.models.SubmissionCode
    template_name = 'problems/problem.html'

    def get_success_url(self):
        kwargs = self.kwargs.copy()
        kwargs['submission'] = self.submission_code.pk
        return reverse('training:submission', kwargs=kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        year, event_type, challenge, problem = get_problem(self.kwargs)

        context['problem'] = problem
        context['languages'] = list(Language)
        context['challenge'] = challenge

        tackled_by = list(problems.models.Submission.objects.filter(challenge=challenge.name,
                                                                    problem=problem.name))
        context['meta_tackled_by'] = len(tackled_by)
        # Could also be written tackled_by.filter(score__gt=0).count() but
        # 1. would do two queries 2. would fail if succeeded() impl changes
        context['meta_solved_by'] = sum(1 for sub in tackled_by if sub.succeeded())

        user_submission = None
        if self.request.user.is_authenticated():
            user_submission = (self.request.user.training_submissions
                               .prefetch_related('codes', 'submission_choices')
                               .filter(challenge=challenge.name, problem=problem.name)
                               .first())
        context['user_submission'] = user_submission

        # load forked submission if wanted, and if everything is fine (right user)
        # TODO: allow is_staff to fork other's submissions
        prefill_submission = None
        try:
            prefill_submission = (problems.models.SubmissionCode.objects.select_related('submission', 'submission__user')
                                                                        .get(pk=int(self.request.GET['fork']),
                                                                             submission__problem=problem.name,
                                                                             submission__challenge=challenge.name,
                                                                             submission__user=self.request.user))
        except (KeyError, ValueError, ObjectDoesNotExist):  # no "fork=", invalid fork id, non-existing fork id
            pass
        context['prefill_submission'] = prefill_submission

        return context

    def form_valid(self, form):
        if not self.request.user.is_authenticated():
            return HttpResponseForbidden()
        context = self.get_context_data()
        self.submission_code = form.save(commit=False)
        submission = context['user_submission']
        if not submission:
            # first code submission; create parent submission
            submission = problems.models.Submission(user=self.request.user,
                                                    challenge=context['challenge'].name,
                                                    problem=context['problem'].name)
            submission.save()
        self.submission_code.submission = submission
        self.submission_code.celery_task_id = celery.uuid()
        self.submission_code.save()

        # FIXME: according to the challenge type (qualif, semifinals) we need to
        # do something different here:
        #  - check (if training or qualif)
        #  - check and unlock (if semifinals)

        # schedule correction
        future = submit_problem_code.apply_async(args=[self.submission_code.pk],
                                                 task_id=self.submission_code.celery_task_id,
                                                 throw=False)
        try:
            # wait a bit for the result, but not too much to prevent the site from looking buggy
            future.get(timeout=settings.TRAINING_RESULT_TIMEOUT)
        except celery.exceptions.TimeoutError:
            pass
        # we don't use super() because CreateView.form_valid() calls form.save() which overrides
        # the code submission, even if it is modified by the correction task!
        return super(ModelFormMixin, self).form_valid(form)


class Submission(DetailView):
    model = problems.models.SubmissionCode
    context_object_name = 'submission'
    template_name = 'problems/submission.html'

    def get_object(self, queryset=None):
        submission_code = self.model.objects.select_related('submission', 'submission__user').get(pk=self.kwargs['submission'])
        return submission_code

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        year, event_type, challenge, problem = get_problem(self.kwargs)
        context['challenge'] = challenge
        context['problem'] = problem
        return context


class SearchProblems(ListView):
    context_object_name = 'problems'
    template_name = 'problems/search_results.html'
    paginate_by = 20
    allow_empty = True

    def get(self, request, *args, **kwargs):
        self.form = SearchForm(self.request.GET if self.request.GET else None)
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        all_results = []
        filter = Q()
        if self.form.is_valid():
            query = self.form.cleaned_data['query']
            event_type = self.form.cleaned_data['event_type']
            difficulty_min = self.form.cleaned_data['difficulty_min']
            difficulty_max = self.form.cleaned_data['difficulty_max']
            for challenge in problems.models.Challenge.all():
                if not challenge.displayable:
                    continue
                if event_type and challenge.event_type.name == event_type:
                    continue
                for problem in challenge.problems:
                    if difficulty_min is not None and problem.difficulty < difficulty_min:
                        continue
                    if difficulty_max is not None and problem.difficulty > difficulty_max:
                        continue
                    if not query or query in problem.title.lower():
                        filter |= Q(challenge=challenge.name, problem=problem.name)
                        all_results.append(problem)

        if self.request.user.is_authenticated():
            # To display user score on each problem
            submissions = get_user_submissions(self.request.user,
                                               extra_filters=filter)
            submissions = {(sub.challenge, sub.problem): sub for sub in submissions}
            for problem in all_results:
                problem.submission = submissions.get((problem.challenge.name, problem.name))

        all_results.sort(key=lambda p: p.title.lower())
        return all_results

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_form'] = self.form
        return context


class AjaxSubmissionCorrected(BaseDetailView):
    model = problems.models.SubmissionCode
    pk_url_kwarg = 'submission'

    def render_to_response(self, context):
        has_result = self.object.done()
        return JsonResponse(has_result, safe=False)


class LegacyChallengeRedirect(RedirectView):
    permanent = False
    legacy_mapping = {
        'qcm': Event.Type.qualification,
        'demi': Event.Type.semifinal,
    }

    def parse(self):
        return self.kwargs['year'], LegacyChallengeRedirect.legacy_mapping[self.kwargs['type']].name

    def get_redirect_url(self, *args, **kwargs):
        year, event_type = self.parse()
        return reverse('training:challenge', kwargs={'year': year,
                                                     'type': event_type})


class LegacyProblemRedirect(LegacyChallengeRedirect):
    def get_redirect_url(self, *args, **kwargs):
        year, event_type = super().parse()
        return reverse('training:problem', kwargs={'year': year,
                                                   'type': event_type,
                                                   'problem': self.kwargs['problem']})
