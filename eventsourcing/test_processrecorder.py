import os
from abc import ABC, abstractmethod
from timeit import timeit
from unittest.case import TestCase
from uuid import uuid4

import psycopg2.errors
from psycopg2.errorcodes import UNDEFINED_TABLE

from eventsourcing.poporecorders import POPOProcessRecorder
from eventsourcing.postgresrecorders import PostgresProcessRecorder
from eventsourcing.tracking import Tracking
from eventsourcing.recorders import RecordConflictError
from eventsourcing.sqliterecorders import (
    SQLiteDatabase,
    SQLiteProcessRecorder,
)
from eventsourcing.storedevent import StoredEvent


class ProcessRecordsTestCase(TestCase, ABC):
    @abstractmethod
    def create_recorder(self):
        pass

    def test_insert_select(self):
        # Construct the recorder.
        recorder = self.create_recorder()

        # Get current position.
        self.assertEqual(
            recorder.max_tracking_id("upstream_app"),
            0,
        )

        # Write two stored events.
        originator_id1 = uuid4()
        originator_id2 = uuid4()

        stored_event1 = StoredEvent(
            originator_id=originator_id1,
            originator_version=0,
            topic="topic1",
            state=b"state1",
        )
        stored_event2 = StoredEvent(
            originator_id=originator_id1,
            originator_version=1,
            topic="topic2",
            state=b"state2",
        )
        stored_event3 = StoredEvent(
            originator_id=originator_id2,
            originator_version=1,
            topic="topic3",
            state=b"state3",
        )
        tracking1 = Tracking(
            application_name="upstream_app",
            notification_id=1,
        )
        tracking2 = Tracking(
            application_name="upstream_app",
            notification_id=2,
        )

        recorder.insert_events(
            stored_events=[
                stored_event1,
                stored_event2,
            ],
            tracking=tracking1,
        )

        # Get current position.
        self.assertEqual(
            recorder.max_tracking_id("upstream_app"),
            1,
        )

        with self.assertRaises(
            RecordConflictError
        ):
            recorder.insert_events(
                stored_events=[stored_event3],
                tracking=tracking1,
            )

        # Get current position.
        self.assertEqual(
            recorder.max_tracking_id("upstream_app"),
            1,
        )

        recorder.insert_events(
            stored_events=[stored_event3],
            tracking=tracking2,
        )

        # Get current position.
        self.assertEqual(
            recorder.max_tracking_id("upstream_app"),
            2,
        )

    def test_performance(self):

        # Construct the recorder.
        recorder = self.create_recorder()

        number = 100

        notification_ids = iter(range(1, number + 1))

        def insert():
            originator_id = uuid4()

            stored_event = StoredEvent(
                originator_id=originator_id,
                originator_version=0,
                topic="topic1",
                state=b"state1",
            )
            tracking1 = Tracking(
                application_name="upstream_app",
                notification_id=next(notification_ids),
            )

            recorder.insert_events(
                stored_events=[
                    stored_event,
                ],
                tracking=tracking1,
            )

        duration = timeit(insert, number=number)
        print(self, f"{duration / number:.9f}")


class TestSQLiteProcessRecorder(ProcessRecordsTestCase):
    def create_recorder(self):
        recorder = SQLiteProcessRecorder(
            SQLiteDatabase(":memory:")
        )
        recorder.create_table()
        return recorder


class TestPOPOProcessRecorder(ProcessRecordsTestCase):
    def create_recorder(self):
        return POPOProcessRecorder()

    def test_performance(self):
        super().test_performance()


class TestPostgresProcessRecorder(ProcessRecordsTestCase):
    def setUp(self) -> None:
        recorder = PostgresProcessRecorder(
            "",
            os.getenv("POSTGRES_DBNAME", "eventsourcing"),
            os.getenv("POSTGRES_HOST", "127.0.0.1"),
            os.getenv("POSTGRES_USER", "eventsourcing"),
            os.getenv("POSTGRES_PASSWORD", "eventsourcing"),
        )
        try:
            with recorder.db.transaction() as c:
                c.execute("DROP TABLE stored_events;")
        except psycopg2.errors.lookup(UNDEFINED_TABLE):
            pass
        try:
            with recorder.db.transaction() as c:
                c.execute("DROP TABLE tracking;")
        except psycopg2.errors.lookup(UNDEFINED_TABLE):
            pass

    def create_recorder(self):
        recorder = PostgresProcessRecorder(
            "",
            os.getenv("POSTGRES_DBNAME", "eventsourcing"),
            os.getenv("POSTGRES_HOST", "127.0.0.1"),
            os.getenv("POSTGRES_USER", "eventsourcing"),
            os.getenv("POSTGRES_PASSWORD", "eventsourcing"),
        )
        recorder.create_table()
        return recorder

    def test_performance(self):
        super().test_performance()


del ProcessRecordsTestCase