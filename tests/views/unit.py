# -*- coding: utf-8 -*-
#
# Copyright (C) Pootle contributors.
#
# This file is a part of the Pootle project. It is distributed under the GPL3
# or later license. See the LICENSE file for a copy of the license and the
# AUTHORS file for copyright and authorship information.

import json
import pytest

from django.http import Http404

from pytest_pootle.utils import create_api_request

from translate.misc.multistring import multistring

from pootle.core.exceptions import Http400
from pootle_app.models.permissions import check_permission
from pootle_comment import get_model as get_comment_model
from pootle_statistics.models import Submission, SubmissionTypes
from pootle_store.constants import TRANSLATED, UNTRANSLATED
from pootle_store.models import QualityCheck, Suggestion, Unit, UnitChange
from pootle_store.views import get_units, toggle_qualitycheck


@pytest.mark.django_db
def test_get_units(rf, default):
    """Tests units can be retrieved."""
    view = get_units

    # `path` query parameter missing
    request = create_api_request(rf, user=default)
    with pytest.raises(Http400):
        view(request)

    # `path` query parameter present
    request = create_api_request(rf, url='/?path=foo', user=default)
    with pytest.raises(Http404):
        view(request)


@pytest.mark.django_db
def test_get_units_ordered(rf, default, admin, numbered_po):
    """Tests units can be retrieved while applying order filters."""
    view = get_units
    tp = numbered_po.translation_project
    url = (
        '/?path=/%s/%s/&filter=incomplete&sort=newest&initial=true'
        % (tp.language.code, tp.project.code))

    request = create_api_request(rf, url=url, user=default)
    response = view(request)
    assert response.status_code == 200

    request = create_api_request(rf, url=url, user=admin)
    response = view(request)
    assert response.status_code == 200


@pytest.mark.django_db
def test_submit_with_suggestion_and_comment(client, request_users,
                                            settings, system):
    """Tests translation can be applied after suggestion is accepted."""
    settings.POOTLE_CAPTCHA_ENABLED = False
    Comment = get_comment_model()
    unit = Unit.objects.filter(suggestion__state='pending',
                               state=UNTRANSLATED)[0]
    sugg = Suggestion.objects.filter(unit=unit, state='pending')[0]
    user = request_users["user"]
    if user.username != "nobody":
        client.login(
            username=user.username,
            password=request_users["password"])

    url = '/xhr/units/%d/' % unit.id
    edited_target = "Edited %s" % sugg.target_f
    comment = 'This is a comment!'

    response = client.post(
        url,
        {
            'state': False,
            'target_f_0': edited_target,
            'suggestion': sugg.id,
            'comment': comment
        },
        HTTP_X_REQUESTED_WITH='XMLHttpRequest'
    )

    suggestion = Suggestion.objects.get(id=sugg.id)
    unit = Unit.objects.get(id=unit.id)
    if check_permission('translate', response.wsgi_request):
        assert response.status_code == 200

        content = json.loads(response.content)

        assert content['newtargets'] == [edited_target]
        assert content['user_score'] == response.wsgi_request.user.public_score
        assert content['checks'] is None
        unit_source = unit.unit_source.get()
        assert unit_source.created_by == system
        assert unit_source.created_with == SubmissionTypes.SYSTEM
        assert unit.change.submitted_by == suggestion.user
        assert unit.change.reviewed_by == user
        assert unit.change.changed_with == SubmissionTypes.NORMAL

        assert suggestion.state == 'accepted'
        assert str(unit.target) == edited_target
        assert (Comment.objects
                       .for_model(suggestion)
                       .get().comment == comment)
    else:
        assert response.status_code == 403
        assert suggestion.state == "pending"
        assert unit.target == ""
        with pytest.raises(UnitChange.DoesNotExist):
            unit.change


@pytest.mark.django_db
def test_submit_with_suggestion(client, request_users, settings, system):
    """Tests translation can be applied after suggestion is accepted."""
    settings.POOTLE_CAPTCHA_ENABLED = False
    unit = Unit.objects.filter(suggestion__state='pending',
                               state=UNTRANSLATED).first()
    unit_submissions = Submission.objects.filter(unit=unit)
    unit_submissions_count = unit_submissions.count()
    sugg = Suggestion.objects.filter(unit=unit, state='pending').first()
    user = request_users["user"]
    if user.username != "nobody":
        client.login(
            username=user.username,
            password=request_users["password"])

    url = '/xhr/units/%d/' % unit.id

    response = client.post(
        url,
        {
            'state': False,
            'target_f_0': sugg.target_f,
            'suggestion': sugg.id,
        },
        HTTP_X_REQUESTED_WITH='XMLHttpRequest'
    )

    suggestion = Suggestion.objects.get(id=sugg.id)
    unit = Unit.objects.get(id=unit.id)
    if check_permission('translate', response.wsgi_request):
        assert response.status_code == 200
        unit_source = unit.unit_source.get()
        assert unit_source.created_by == system
        assert unit_source.created_with == SubmissionTypes.SYSTEM
        assert unit.change.submitted_by == suggestion.user
        assert unit.change.reviewed_by == user
        assert unit.change.changed_with == SubmissionTypes.NORMAL
        assert suggestion.state == 'accepted'
        assert str(unit.target) == sugg.target_f
        unit_submissions = unit_submissions.exclude(
            type=SubmissionTypes.SUGG_ACCEPT
        )
        assert (unit_submissions.count() - unit_submissions_count == 0)

    else:
        assert response.status_code == 403
        assert suggestion.state == "pending"
        assert unit.target == ""
        with pytest.raises(UnitChange.DoesNotExist):
            unit.change


@pytest.mark.django_db
def test_accept_suggestion_with_comment(client, request_users, settings, system):
    """Tests suggestion can be accepted with a comment."""
    settings.POOTLE_CAPTCHA_ENABLED = False
    Comment = get_comment_model()
    unit = Unit.objects.filter(suggestion__state='pending',
                               state=UNTRANSLATED)[0]
    sugg = Suggestion.objects.filter(unit=unit, state='pending')[0]
    user = request_users["user"]
    if user.username != "nobody":
        client.login(
            username=user.username,
            password=request_users["password"])

    url = '/xhr/units/%d/suggestions/%d/' % (unit.id, sugg.id)
    comment = 'This is a comment!'
    response = client.post(
        url,
        {
            'comment': comment
        },
        HTTP_X_REQUESTED_WITH='XMLHttpRequest'
    )

    suggestion = Suggestion.objects.get(id=sugg.id)
    unit = Unit.objects.get(id=unit.id)
    if check_permission('review', response.wsgi_request):
        assert response.status_code == 200
        unit_source = unit.unit_source.get()
        assert unit_source.created_by == system
        assert unit_source.created_with == SubmissionTypes.SYSTEM
        assert unit.change.submitted_by == suggestion.user
        assert unit.change.reviewed_by == user
        assert unit.change.changed_with == SubmissionTypes.NORMAL
        assert suggestion.state == 'accepted'
        assert str(unit.target) == str(suggestion.target)
        assert (Comment.objects
                       .for_model(suggestion)
                       .get().comment == comment)
    else:
        assert response.status_code == 403
        assert suggestion.state == "pending"
        assert unit.target == ""
        with pytest.raises(UnitChange.DoesNotExist):
            unit.change


@pytest.mark.django_db
def test_reject_suggestion_with_comment(client, request_users):
    """Tests suggestion can be rejected with a comment."""
    Comment = get_comment_model()
    unit = Unit.objects.filter(suggestion__state='pending',
                               state=UNTRANSLATED)[0]
    sugg = Suggestion.objects.filter(unit=unit, state='pending')[0]
    comment = 'This is a comment!'
    user = request_users["user"]
    if user.username != "nobody":
        client.login(
            username=user.username,
            password=request_users["password"])

    url = '/xhr/units/%d/suggestions/%d/' % (unit.id, sugg.id)
    response = client.delete(
        url,
        'comment=%s' % comment,
        HTTP_X_REQUESTED_WITH='XMLHttpRequest'
    )

    can_reject = (
        check_permission('review', response.wsgi_request)
        or sugg.user.id == user.id
    )
    suggestion = Suggestion.objects.get(id=sugg.id)
    if can_reject:
        assert response.status_code == 200
        assert suggestion.state == 'rejected'
        assert unit.target == ""
        # unit is untranslated so no change
        with pytest.raises(UnitChange.DoesNotExist):
            unit.change
        assert (Comment.objects
                       .for_model(suggestion)
                       .get().comment == comment)
    else:
        assert response.status_code == 403
        assert unit.target == ""
        assert suggestion.state == "pending"
        with pytest.raises(UnitChange.DoesNotExist):
            unit.change


@pytest.mark.django_db
def test_reject_translated_suggestion(client, request_users, member, system):
    """Tests suggestion can be rejected with a comment."""
    unit = Unit.objects.filter(
        suggestion__state='pending',
        state=UNTRANSLATED)[0]
    unit.target = "EXISTING TARGET"
    unit.save(
        submitted_by=member,
        changed_with=SubmissionTypes.UPLOAD)
    suggestion = Suggestion.objects.filter(
        unit=unit,
        state='pending')[0]
    user = request_users["user"]
    if user.username != "nobody":
        client.login(
            username=user.username,
            password=request_users["password"])
    url = (
        '/xhr/units/%d/suggestions/%d/'
        % (unit.id, suggestion.id))
    response = client.delete(
        url,
        HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    can_reject = (
        check_permission('review', response.wsgi_request)
        or suggestion.user.id == user.id)
    unit.refresh_from_db()
    unit.change.refresh_from_db()
    unit_source = unit.unit_source.get()
    suggestion.refresh_from_db()
    if can_reject:
        assert response.status_code == 200
        assert suggestion.state == 'rejected'
        assert unit_source.created_by == system
        assert unit.change.changed_with == SubmissionTypes.UPLOAD
        assert unit.change.submitted_by == member
        assert unit.change.reviewed_by == user
    else:
        assert response.status_code == 403
        assert unit.target == "EXISTING TARGET"
        assert suggestion.state == "pending"


@pytest.mark.django_db
def test_toggle_quality_check(rf, admin):
    """Tests the view that mutes/unmutes quality checks."""
    qc_filter = dict(
        false_positive=False,
        unit__state=TRANSLATED,
        unit__store__translation_project__project__disabled=False,
    )
    qc = QualityCheck.objects.filter(**qc_filter).first()
    unit = qc.unit

    # Explicit POST data present, mute
    data = 'mute='
    request = create_api_request(rf, method='post', user=admin, data=data,
                                 encode_as_json=False)
    response = toggle_qualitycheck(request, unit.id, qc.id)
    assert response.status_code == 200
    assert QualityCheck.objects.get(id=qc.id).false_positive is True

    # No POST data present, unmute
    request = create_api_request(rf, method='post', user=admin)
    response = toggle_qualitycheck(request, unit.id, qc.id)
    assert response.status_code == 200
    assert QualityCheck.objects.get(id=qc.id).false_positive is False


@pytest.mark.django_db
def test_submit_unit_plural(client, unit_plural, request_users, settings):
    """Tests translation can be applied after suggestion is accepted."""
    settings.POOTLE_CAPTCHA_ENABLED = False
    user = request_users["user"]
    if user.username != "nobody":
        client.login(
            username=user.username,
            password=request_users["password"])

    url = '/xhr/units/%d/' % unit_plural.id
    original_target = unit_plural.target
    target = [
        "%s" % unit_plural.target.strings[0],
        "%s changed" % unit_plural.target.strings[1]
    ]
    response = client.post(
        url,
        {
            'target_f_0': target[0],
            'target_f_1': target[1],
        },
        HTTP_X_REQUESTED_WITH='XMLHttpRequest'
    )

    unit = Unit.objects.get(id=unit_plural.id)
    if check_permission('translate', response.wsgi_request):
        assert response.status_code == 200
        assert unit.target == multistring(target)
    else:
        assert response.status_code == 403
        assert unit.target == original_target
        with pytest.raises(UnitChange.DoesNotExist):
            unit.change


@pytest.mark.django_db
def test_add_suggestion(client, request_users, settings):
    """Tests translation can be applied after suggestion is accepted."""
    settings.POOTLE_CAPTCHA_ENABLED = False
    user = request_users["user"]
    if user.username != "nobody":
        client.login(
            username=user.username,
            password=request_users["password"])

    unit = Unit.objects.all().first()
    url = '/xhr/units/%d/suggestions' % unit.id
    target = "%s TEST SUGGESTION" % unit.source
    response = client.post(
        url,
        {
            'target_f_0': target,
        },
        HTTP_X_REQUESTED_WITH='XMLHttpRequest'
    )

    assert response.status_code == 200
    changed = Unit.objects.get(id=unit.id)
    suggestion = changed.get_suggestions().order_by('id').last()
    assert suggestion.target == multistring(target)
    with pytest.raises(UnitChange.DoesNotExist):
        unit.change


@pytest.mark.django_db
def test_submit_unit(client, store0, request_users, settings, system):
    """Tests translation can be applied after suggestion is accepted."""
    settings.POOTLE_CAPTCHA_ENABLED = False
    user = request_users["user"]
    unit = store0.units.filter(state=UNTRANSLATED).first()
    if user.username != "nobody":
        client.login(
            username=user.username,
            password=request_users["password"])
    url = '/xhr/units/%d/' % unit.id
    old_target = unit.target
    response = client.post(
        url,
        dict(target_f_0=("%s changed" % unit.target),
             sfn="PTL.editor.processSubmission"),
        HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    unit.refresh_from_db()
    if user.username == "nobody":
        assert response.status_code == 403
        assert unit.target == ""
        with pytest.raises(UnitChange.DoesNotExist):
            unit.change
        return
    assert response.status_code == 200
    assert unit.target == "%s changed" % old_target
    assert unit.state == TRANSLATED
    assert unit.store.data.last_submission.unit == unit
    unit_source = unit.unit_source.get()
    assert unit_source.created_by == system
    assert unit_source.created_with == SubmissionTypes.SYSTEM
    assert unit.change.changed_with == SubmissionTypes.NORMAL
    assert unit.change.submitted_by == user
    assert unit.change.reviewed_by is None
