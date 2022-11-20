from django.core.exceptions import ObjectDoesNotExist

from assessment.services.assessment_event_attempt import validate_user_participation, validate_assessor_participation
from assessment.services import utils as assessment_utils
from one_day_intern.exceptions import InvalidRequestException
from users.services import utils as users_utils


def get_assessee_progress_on_assessment_event(request_data, user):
    try:
        event = assessment_utils.get_assessment_event_from_id(request_data.get('assessment-event-id'))
        assessor = users_utils.get_assessor_from_user(user)
        validate_assessor_participation(event, assessor)
        validate_assessor_participation(event, assessor)
        assessee = assessment_utils.get_assessee_from_email(request_data.get('assessee-email'))
        validate_user_participation(event, assessee)
        return event.get_assessee_progress_on_event(assessee)
    except ObjectDoesNotExist as exception:
        raise InvalidRequestException(str(exception))
