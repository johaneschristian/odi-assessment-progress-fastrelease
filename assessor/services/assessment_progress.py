from django.core.exceptions import ObjectDoesNotExist

from assessment.models import AssessmentEvent
from assessment.services.assessment_event_attempt import validate_assessor_participation
from assessment.services import utils as assessment_utils
from one_day_intern.exceptions import InvalidRequestException, RestrictedAccessException
from users.models import Assessee
from users.services import utils as users_utils


def validate_assessee_participation(assessment_event: AssessmentEvent, assessee: Assessee):
    if not assessment_event.check_assessee_participation(assessee):
        raise InvalidRequestException(
            f'Assessee with email {assessee.email} is not part of assessment with id {assessment_event.event_id}'
        )


def validate_responsibility(event, assessor, assessee):
    if not event.check_assessee_and_assessor_pair(assessee, assessor):
        raise RestrictedAccessException(f'{assessor} is not responsible for {assessee} on event with id {event.event_id}')


def get_assessee_progress_on_assessment_event(request_data, user):
    try:
        event = assessment_utils.get_assessment_event_from_id(request_data.get('assessment-event-id'))
        assessor = users_utils.get_assessor_from_user(user)
        validate_assessor_participation(event, assessor)
        assessee = assessment_utils.get_assessee_from_email(request_data.get('assessee-email'))
        validate_assessee_participation(event, assessee)
        validate_responsibility(event, assessor, assessee)
        return event.get_assessee_progress_on_event(assessee)
    except ObjectDoesNotExist as exception:
        raise InvalidRequestException(str(exception))
