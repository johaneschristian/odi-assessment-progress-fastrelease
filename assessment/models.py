import pytz
from django.db import models
from rest_framework import serializers
from polymorphic.models import PolymorphicModel
from users.models import Assessor, AssessorSerializer
from .services.TaskGenerator import TaskGenerator
from .exceptions.exceptions import AssessmentToolDoesNotExist
from typing import List, Optional
import datetime
import uuid

USERS_COMPANY = 'users.Company'
OWNING_COMPANY_COMPANY_ID = 'owning_company.company_id'
OWNING_COMPANY_COMPANY_NAME = 'owning_company.company_name'


class AssessmentTool(PolymorphicModel):
    assessment_id = models.UUIDField(primary_key=True, auto_created=True, default=uuid.uuid4)
    name = models.CharField(max_length=50, null=False)
    description = models.TextField(null=True)
    owning_company = models.ForeignKey(USERS_COMPANY, on_delete=models.CASCADE)

    def get_tool_data(self) -> dict:
        return {
            'name': self.name,
            'description': self.description
        }

    def get_tool_type(self) -> str:
        return str(type(self)).lower()


class AssessmentToolSerializer(serializers.ModelSerializer):
    owning_company_id = serializers.ReadOnlyField(source=OWNING_COMPANY_COMPANY_ID)

    class Meta:
        model = AssessmentTool
        fields = ['assessment_id', 'name', 'description', 'owning_company_id']


class Assignment(AssessmentTool):
    expected_file_format = models.CharField(max_length=5, null=True)
    duration_in_minutes = models.IntegerField(null=False)

    def get_tool_data(self) -> dict:
        tool_base_data = super().get_tool_data()
        tool_base_data['type'] = 'assignment'
        tool_base_data['additional_info'] = {
            'duration': self.duration_in_minutes,
            'expected_file_format': self.expected_file_format
        }
        return tool_base_data

    def get_end_working_time(self, start_time: datetime.time):
        temporary_datetime = datetime.datetime(2000, 1, 1, start_time.hour, start_time.minute, start_time.second)
        temporary_datetime = temporary_datetime + datetime.timedelta(minutes=self.duration_in_minutes)
        return temporary_datetime.time()


class AssignmentSerializer(serializers.ModelSerializer):
    owning_company_name = serializers.ReadOnlyField(source=OWNING_COMPANY_COMPANY_NAME)

    class Meta:
        model = Assignment
        fields = [
            'assessment_id',
            'name',
            'description',
            'expected_file_format',
            'duration_in_minutes',
            'owning_company_id',
            'owning_company_name'
        ]


class InteractiveQuiz(AssessmentTool):
    duration_in_minutes = models.IntegerField(null=False)
    total_points = models.IntegerField(null=False)


class Question(models.Model):
    TYPES_CHOICES = [
        ('text', 'Text Question'),
        ('multiple_choice', 'Multiple Choice Question')
    ]

    interactive_quiz = models.ForeignKey(InteractiveQuiz, related_name='questions', on_delete=models.CASCADE)
    prompt = models.TextField(null=False)
    points = models.IntegerField(default=0)
    question_type = models.CharField(choices=TYPES_CHOICES, null=False, max_length=16)


class MultipleChoiceQuestion(Question):
    def get_answer_options(self):
        return self.multiplechoiceansweroption_set

    def save_answer_option_to_database(self, answer: dict):
        content = answer.get('content')
        correct = answer.get('correct')

        answer_option = MultipleChoiceAnswerOption.objects.create(
            question=self,
            content=content,
            correct=correct
        )

        return answer_option


class MultipleChoiceAnswerOption(models.Model):
    question = models.ForeignKey('MultipleChoiceQuestion', related_name='questions', on_delete=models.CASCADE)
    content = models.TextField(null=False)
    correct = models.BooleanField(default=False)


class TextQuestion(Question):
    answer_key = models.TextField(null=True)


class MultipleChoiceAnswerOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MultipleChoiceAnswerOption
        fields = [
            'content',
            'correct'
        ]


class MultipleChoiceQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MultipleChoiceQuestion
        fields = [
            'prompt',
            'points',
            'question_type',
        ]


class TextQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TextQuestion
        fields = [
            'prompt',
            'points',
            'question_type',
            'answer_key'
        ]


def to_representation(instance):
    if isinstance(instance, MultipleChoiceQuestion):
        return MultipleChoiceQuestionSerializer(instance=instance).data
    elif isinstance(instance, TextQuestion):
        return TextQuestionSerializer(instance=instance).data


class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TextQuestion
        fields = [
            'prompt',
            'points',
            'question_type',
        ]


class InteractiveQuizSerializer(serializers.ModelSerializer):
    owning_company_name = serializers.ReadOnlyField(source=OWNING_COMPANY_COMPANY_NAME)

    class Meta:
        model = InteractiveQuiz
        fields = [
            'assessment_id',
            'name',
            'description',
            'total_points',
            'duration_in_minutes',
            'owning_company_id',
            'owning_company_name'
        ]


class TestFlow(models.Model):
    test_flow_id = models.UUIDField(default=uuid.uuid4, auto_created=True)
    name = models.CharField(max_length=50)
    owning_company = models.ForeignKey(USERS_COMPANY, on_delete=models.CASCADE)
    tools = models.ManyToManyField(AssessmentTool, through='TestFlowTool')
    is_usable = models.BooleanField(default=False)

    def add_tool(self, assessment_tool, release_time, start_working_time):
        self.is_usable = True
        TestFlowTool.objects.create(
            assessment_tool=assessment_tool,
            test_flow=self,
            release_time=release_time,
            start_working_time=start_working_time
        )
        self.save()

    def get_is_usable(self):
        return self.is_usable

    def get_tools_data(self) -> List[dict]:
        test_flow_tools = TestFlowTool.objects.filter(test_flow=self)
        return [test_flow_tool.get_release_time_and_assessment_data() for test_flow_tool in test_flow_tools]

    def get_tools(self):
        return self.tools.all()


class TestFlowTool(models.Model):
    assessment_tool = models.ForeignKey('assessment.AssessmentTool', on_delete=models.CASCADE)
    test_flow = models.ForeignKey(TestFlow, on_delete=models.CASCADE)
    release_time = models.TimeField(auto_now=False, auto_now_add=False, default=datetime.time(0, 0))
    start_working_time = models.TimeField(auto_now=False, auto_now_add=False, default=datetime.time(0, 0))

    class Meta:
        ordering = ['release_time']
        get_latest_by = 'release_time'

    def get_release_time_and_assessment_data(self) -> (str, dict):
        return {
            'release_time': str(self.release_time),
            'assessment_data': self.assessment_tool.get_tool_data()
        }

    def release_time_has_passed(self):
        return self.release_time <= datetime.datetime.now().time()

    def get_released_tool_data(self) -> dict:
        """
        Data format for assignment
        {
            'id': '19bn-jabc8-'
            'type': 'assignment',
            'name': 'assignment name',
            'description': 'Description ...',
            'additional_info': {
                'duration': 180,
                'expected_file_format': 'pdf'
            },
            'released_time': '12:00:00',
            'end_working_time': '15:00:00' (release-time + duration)
        }
        """
        released_data = self.assessment_tool.get_tool_data()
        released_data['id'] = str(self.assessment_tool.assessment_id)

        if isinstance(self.assessment_tool, Assignment):
            released_data['released_time'] = str(self.release_time)
            released_data['end_working_time'] = str(
                self.assessment_tool.get_end_working_time(start_time=self.release_time))

        return released_data


class TestFlowToolSerializer(serializers.ModelSerializer):
    assessment_tool = AssessmentToolSerializer(read_only=True)
    test_flow_id = serializers.ReadOnlyField(source='test_flow.test_flow_id')

    class Meta:
        model = TestFlowTool
        fields = ['assessment_tool', 'test_flow_id', 'release_time']


class TestFlowSerializer(serializers.ModelSerializer):
    owning_company_id = serializers.ReadOnlyField(source=OWNING_COMPANY_COMPANY_ID)
    tools = TestFlowToolSerializer(source='testflowtool_set', read_only=True, many=True)

    class Meta:
        model = TestFlow
        fields = ['test_flow_id', 'name', 'owning_company_id', 'is_usable', 'tools']


class AssessmentEvent(models.Model):
    event_id = models.UUIDField(default=uuid.uuid4, auto_created=True)
    name = models.CharField(max_length=50)
    start_date_time = models.DateTimeField()
    owning_company = models.ForeignKey(USERS_COMPANY, on_delete=models.CASCADE)
    test_flow_used = models.ForeignKey('assessment.TestFlow', on_delete=models.RESTRICT)

    def check_company_ownership(self, company):
        return self.owning_company.company_id == company.company_id

    def add_participant(self, assessee, assessor):
        if not self.check_assessee_participation(assessee):
            assessment_event_participation = AssessmentEventParticipation.objects.create(
                assessment_event=self,
                assessee=assessee,
                assessor=assessor
            )

            test_flow_attempt = TestFlowAttempt.objects.create(
                event_participation=assessment_event_participation,
                test_flow_attempted=self.test_flow_used
            )

            VideoConferenceRoom.objects.create(
                part_of=assessment_event_participation
            )

            assessment_event_participation.attempt = test_flow_attempt
            assessment_event_participation.save()

            return assessment_event_participation

    def check_assessee_participation(self, assessee):
        found_assessees = AssessmentEventParticipation.objects.filter(
            assessment_event=self,
            assessee=assessee
        )
        return found_assessees.exists()

    def check_assessor_participation(self, assessor):
        found_assessors = AssessmentEventParticipation.objects.filter(
            assessment_event=self,
            assessor=assessor
        )
        return found_assessors.exists()

    def get_task_generator(self):
        task_generator = TaskGenerator()
        test_flow = self.test_flow_used
        tools_release_and_assignment_data = test_flow.get_tools_data()

        for tool_release_and_assignment_datum in tools_release_and_assignment_data:
            release_time = tool_release_and_assignment_datum['release_time']
            assessment_data = tool_release_and_assignment_datum['assessment_data']
            task_generator.add_task(assessment_data, release_time)

        return task_generator

    def is_active(self) -> bool:
        return self.start_date_time <= datetime.datetime.now(datetime.timezone.utc)

    def get_released_assignments(self):
        test_flow_tools = self.get_tools_of_used_test_flow()
        released_assignments_data = []
        for test_flow_tool in test_flow_tools:
            tool_used = test_flow_tool.assessment_tool
            if isinstance(tool_used, Assignment) and test_flow_tool.release_time_has_passed():
                released_assignments_data.append(test_flow_tool.get_released_tool_data())

        return released_assignments_data

    def get_assessment_event_participation_by_assessee(self, assessee):
        return self.assessmenteventparticipation_set.get(assessee=assessee)

    def get_assessment_tool_from_assessment_id(self, assessment_id):
        found_assessment_tools = self.test_flow_used.tools.filter(
            assessment_id=assessment_id
        )
        if found_assessment_tools:
            return found_assessment_tools[0]

        else:
            raise AssessmentToolDoesNotExist(
                f'Tool with id {assessment_id} associated with event with id {self.event_id} is not found'
            )

    def get_tools_of_used_test_flow(self):
        return self.test_flow_used.get_tools()

    def check_if_tool_is_submittable(self, assessment_tool):
        pass


class AssessmentEventSerializer(serializers.ModelSerializer):
    owning_company_id = serializers.ReadOnlyField(source=OWNING_COMPANY_COMPANY_ID)
    test_flow_id = serializers.ReadOnlyField(source='test_flow_used.test_flow_id')

    class Meta:
        model = AssessmentEvent
        fields = ['event_id', 'name', 'start_date_time', 'owning_company_id', 'test_flow_id']


class TestFlowAttempt(models.Model):
    attempt_id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    note = models.TextField(null=True)
    grade = models.FloatField(default=0)
    event_participation = models.ForeignKey('assessment.AssessmentEventParticipation', on_delete=models.CASCADE)
    test_flow_attempted = models.ForeignKey('assessment.TestFlow', on_delete=models.RESTRICT)


class ResponseTest(AssessmentTool):
    sender = models.ForeignKey('users.Assessor', on_delete=models.CASCADE)
    subject = models.TextField(null=False)
    prompt = models.TextField(null=False)


class ResponseTestSerializer(serializers.ModelSerializer):
    owning_company_name = serializers.ReadOnlyField(source=OWNING_COMPANY_COMPANY_NAME)
    sender = serializers.ReadOnlyField(source='sender.email')
    class Meta:
        model = ResponseTest
        fields = [
            'assessment_id',
            'name',
            'description',
            'subject',
            'prompt',
            'sender',
            'owning_company_id',
            'owning_company_name',
        ]


class PolymorphicAssessmentToolSerializer:
    def __init__(self, instance):
        self.instance = instance
        self.data = self.get_serializer().data

    def get_serializer(self):
        if isinstance(self.instance, Assignment):
            return AssignmentSerializer(self.instance)
        if isinstance(self.instance, InteractiveQuiz):
            return InteractiveQuizSerializer(self.instance)
        if isinstance(self.instance, ResponseTest):
            return ResponseTestSerializer(self.instance)


class VideoConferenceRoom(models.Model):
    part_of = models.ForeignKey('assessment.AssessmentEventParticipation', on_delete=models.CASCADE)
    room_id = models.TextField(null=True, default=None)
    conference_participants = models.ManyToManyField('users.Assessor')
    room_opened = models.BooleanField(default=False)

    def is_room_created(self) -> bool:
        return self.room_id != None

    def is_room_opened(self) -> bool:
        return self.room_opened

    def is_already_participated_by(self, assessor: Assessor):
        """
        return True if query list is not empty, False otherwise
        """
        return self.conference_participants.filter(email=assessor.email)


class VideoConferenceRoomSerializer(serializers.ModelSerializer):
    conference_host = serializers.ReadOnlyField(source='part_of.assessor.email')
    conference_assessee = serializers.ReadOnlyField(source='part_of.assessee.email')
    conference_participants = AssessorSerializer(read_only=True, many=True)
    conference_in_assessment_event = serializers.ReadOnlyField(source='part_of.assessment_event.event_id')

    class Meta:
        model = VideoConferenceRoom
        fields = ['room_id', 'conference_in_assessment_event', 'conference_host', 'conference_assessee', 'room_opened', 'conference_participants']


class ToolAttempt(PolymorphicModel):
    tool_attempt_id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    grade = models.FloatField(default=0)
    test_flow_attempt = models.ForeignKey('assessment.TestFlowAttempt', on_delete=models.CASCADE)
    assessment_tool_attempted = models.ForeignKey('assessment.AssessmentTool', on_delete=models.CASCADE, default=None)


class AssignmentAttempt(ToolAttempt):
    file_upload_directory = models.TextField(null=True)
    filename = models.TextField(default=None, null=True)
    submitted_time = models.DateTimeField(default=None, null=True)

    def update_attempt_cloud_directory(self, file_upload_directory):
        self.submitted_time = datetime.datetime.now(tz=pytz.utc)
        self.file_upload_directory = file_upload_directory
        self.save()

    def get_attempt_cloud_directory(self):
        return self.file_upload_directory

    def update_file_name(self, filename):
        self.filename = filename
        self.save()

    def get_file_name(self):
        return self.filename

    def get_submitted_time(self):
        return self.submitted_time


class AssessmentEventParticipation(models.Model):
    assessment_event = models.ForeignKey('assessment.AssessmentEvent', on_delete=models.CASCADE)
    assessee = models.ForeignKey('users.Assessee', on_delete=models.CASCADE)
    assessor = models.ForeignKey('users.Assessor', on_delete=models.RESTRICT)
    attempt = models.OneToOneField('assessment.TestFlowAttempt', on_delete=models.CASCADE, null=True)

    def get_all_assignment_attempts(self):
        return self.attempt.toolattempt_set.instance_of(AssignmentAttempt)

    def get_assignment_attempt(self, assignment: Assignment) -> Optional[AssignmentAttempt]:
        assignment_attempts = self.get_all_assignment_attempts()
        matching_assignment_attempts = assignment_attempts.filter(assessment_tool_attempted=assignment)

        if matching_assignment_attempts:
            return matching_assignment_attempts[0]

        else:
            return None

    def create_assignment_attempt(self, assignment: Assignment) -> AssignmentAttempt:
        assignment_attempt = AssignmentAttempt.objects.create(
            test_flow_attempt=self.attempt,
            assessment_tool_attempted=assignment
        )
        return assignment_attempt

    def get_all_assessment_tool_attempts(self):
        return self.attempt.toolattempt_set.all()

    def get_assessment_tool_attempt(self, assessment_tool: AssessmentTool):
        tool_attempts = self.get_all_assessment_tool_attempts()
        matching_tool_attempts = tool_attempts.filter(assessment_tool_attempted=assessment_tool)

        if matching_tool_attempts:
            return matching_tool_attempts[0]

        else:
            return None

    def get_assessment_tool_attempt_id(self, assessment_tool):
        found_attempt = self.get_assessment_tool_attempt(assessment_tool)
        if found_attempt:
            attempt_id = found_attempt.attempt_id
        else:
            attempt_id = None

        return attempt_id

    def get_attempt_to_test_flow_tools(self):
        test_flow_tools = self.assessment_event.get_tools_of_used_test_flow()

        attempt_of_flow = []
        for test_flow_tool in test_flow_tools:
            tool_and_attempt_data = {
                'tool-data': PolymorphicAssessmentToolSerializer(test_flow_tool).data,
                'attempt-id': self.get_assessment_tool_attempt_id(test_flow_tool),
                'type': test_flow_tool.get_tool_type()
            }
            attempt_of_flow.append(tool_and_attempt_data)

        return attempt_of_flow


class AssessmentEventParticipationSerializer(serializers.ModelSerializer):
    assessment_event_id = serializers.ReadOnlyField(source='assessment_event.assessment_event_id')
    assessee_id = serializers.ReadOnlyField(source='assessee.assessee_id')
    assessor_id = serializers.ReadOnlyField(source='assessor.assessor_id')

    class Meta:
        model = AssessmentEventParticipation
        fields = ['assessment_event_id', 'assessee_id', 'assessor_id']


class TestFlowAttemptSerializer(serializers.ModelSerializer):
    event_participation = AssessmentEventParticipationSerializer(source='assessmenteventparticipation', read_only=True)
    test_flow_attempted_id = serializers.ReadOnlyField(source='test_flow_attempted.test_flow_attempted_id')

    class Meta:
        model = TestFlowAttempt
        fields = ['attempt_id', 'note', 'grade', 'event_participation', 'test_flow_attempted_id']


class TestFlowAttemptSerializer(serializers.ModelSerializer):
    event_participation = AssessmentEventParticipationSerializer(source='assessmenteventparticipation', read_only=True)
    test_flow_attempted_id = serializers.ReadOnlyField(source='test_flow_attempted.test_flow_attempted_id')

    class Meta:
        model = TestFlowAttempt
        fields = ['attempt_id', 'note', 'grade', 'event_participation', 'test_flow_attempted_id']