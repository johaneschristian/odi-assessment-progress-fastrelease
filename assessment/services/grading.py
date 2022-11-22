import mimetypes

from django.core.exceptions import ObjectDoesNotExist
from one_day_intern.exceptions import RestrictedAccessException, InvalidRequestException
from one_day_intern.settings import GOOGLE_STORAGE_BUCKET_NAME
from users.services import utils as user_utils
from .assessment_event_attempt import validate_assessor_participation
from . import utils, google_storage
from ..models import AssignmentAttempt, ToolAttempt


def validate_grade_assessment_tool_request(request_data):
    if not request_data.get('tool-attempt-id'):
        raise InvalidRequestException('Tool attempt id must exist')
    if not request_data.get('grade'):
        raise InvalidRequestException('Grade must exist')
    if not isinstance(request_data.get('grade'), (float, int)):
        raise InvalidRequestException('Grade must be an integer or a floating point number')


def validate_assessor_responsibility(event, assessor, assessee):
    if not event.check_assessee_and_assessor_pair(assessee, assessor):
        raise RestrictedAccessException(f'{assessor} is not responsible for {assessee} on event with id {event.event_id}')


def get_assessor_or_raise_exception(user):
    try:
        return user_utils.get_assessor_from_user(user)
    except ObjectDoesNotExist as exception:
        raise RestrictedAccessException(str(exception))


def set_grade_and_note_of_tool_attempt(tool_attempt, request_data):
    tool_attempt.set_grade(request_data.get('grade'))

    if request_data.get('note'):
        tool_attempt.set_note(request_data.get('note'))


def grade_assessment_tool(request_data, user):
    try:
        validate_grade_assessment_tool_request(request_data)
        tool_attempt = utils.get_tool_attempt_from_id(request_data.get('tool-attempt-id'))
        assessor = get_assessor_or_raise_exception(user)
        event = tool_attempt.get_event_of_attempt()
        validate_assessor_participation(event, assessor)
        assessee = tool_attempt.get_user_of_attempt()
        validate_assessor_responsibility(event, assessor, assessee)
        set_grade_and_note_of_tool_attempt(tool_attempt, request_data)
        return tool_attempt
    except ObjectDoesNotExist as exception:
        raise InvalidRequestException(str(exception))


def download_assignment_attempt(assignment_attempt: AssignmentAttempt):
    if assignment_attempt.get_attempt_cloud_directory() is not None:
        cloud_storage_file_name = assignment_attempt.get_attempt_cloud_directory()
        expected_content_type = mimetypes.guess_type(assignment_attempt.get_file_name())[0]
        download_file = google_storage.download_file_from_google_bucket(
            cloud_storage_file_name,
            GOOGLE_STORAGE_BUCKET_NAME,
            assignment_attempt.get_file_name(),
            expected_content_type
        )
        return download_file
    else:
        return None


def validate_tool_attempt_is_for_assignment(tool_attempt):
    if not isinstance(tool_attempt, AssignmentAttempt):
        raise InvalidRequestException(f'Attempt with id {tool_attempt.tool_attempt_id} is not an assignment')


def get_submitted_assignment_assessor(request_data, user):
    tool_attempt = utils.get_tool_attempt_from_id(request_data.get('tool-attempt-id'))
    assessor = get_assessor_or_raise_exception(user)
    event = tool_attempt.get_event_of_attempt()
    validate_assessor_participation(event, assessor)
    assessee = tool_attempt.get_user_of_attempt()
    validate_assessor_responsibility(event, assessor, assessee)
    downloaded_file = download_assignment_attempt(tool_attempt)
    return downloaded_file


def get_assignment_attempt_data(request_data, user):
    try:
        tool_attempt = utils.get_tool_attempt_from_id(request_data.get('tool-attempt-id'))
        validate_tool_attempt_is_for_assignment(tool_attempt)
        assessor = get_assessor_or_raise_exception(user)
        event = tool_attempt.get_event_of_attempt()
        validate_assessor_participation(event, assessor)
        assessee = tool_attempt.get_user_of_attempt()
        validate_assessor_responsibility(event, assessor, assessee)
        return tool_attempt
    except ObjectDoesNotExist as exception:
        raise InvalidRequestException(str(exception))

