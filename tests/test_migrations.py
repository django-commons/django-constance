import pickle
from base64 import b64encode
from datetime import date
from datetime import datetime
from importlib import import_module
from unittest import mock

from django.apps import apps
from django.db import connection
from django.test import TestCase

from constance import settings
from constance.codecs import dumps
from constance.codecs import loads
from constance.models import Constance
from tests.redis_mockup import Connection

drop_pickle = import_module("constance.migrations.0003_drop_pickle")

# datetime(2017, 5, 15, 10, 30) and date(2017, 5, 15) as pickled by Python 2, with protocol 2
# (django-picklefield, used by the database backend) and protocol 0 (cPickle default, used by the Redis backend).
PY2_DATETIME = b"\x80\x02cdatetime\ndatetime\nq\x00U\n\x07\xe1\x05\x0f\n\x1e\x00\x00\x00\x00q\x01\x85q\x02Rq\x03."
PY2_DATE = b"\x80\x02cdatetime\ndate\nq\x00U\x04\x07\xe1\x05\x0fq\x01\x85q\x02Rq\x03."
PY2_DATETIME_PROTOCOL_0 = (
    b"cdatetime\ndatetime\np0\n(S'\\x07\\xe1\\x05\\x0f\\n\\x1e\\x00\\x00\\x00\\x00'\np1\ntp2\nRp3\n."
)


class TestDropPickleMigration(TestCase):
    def migrate(self):
        drop_pickle.migrate_pickled_data(apps, connection.schema_editor())

    @mock.patch("constance.settings.BACKEND", "constance.backends.database.DatabaseBackend")
    def test_migrates_database_values(self):
        Constance.objects.bulk_create(
            [
                Constance(key="PY2_DATETIME", value=b64encode(PY2_DATETIME).decode()),
                Constance(key="PY2_DATE", value=b64encode(PY2_DATE).decode()),
                Constance(key="PY3_DATETIME", value=b64encode(pickle.dumps(datetime(2024, 1, 2, 3, 4, 5), 2)).decode()),
                Constance(key="PY3_INT", value=b64encode(pickle.dumps(42)).decode()),
                Constance(key="JSON_STRING", value=dumps("already migrated")),
            ]
        )

        self.migrate()

        self.assertEqual(
            {constance.key: loads(constance.value) for constance in Constance.objects.all()},
            {
                "PY2_DATETIME": datetime(2017, 5, 15, 10, 30),
                "PY2_DATE": date(2017, 5, 15),
                "PY3_DATETIME": datetime(2024, 1, 2, 3, 4, 5),
                "PY3_INT": 42,
                "JSON_STRING": "already migrated",
            },
        )

    @mock.patch("constance.settings.BACKEND", "constance.backends.redisd.RedisBackend")
    def test_migrates_redis_values(self):
        redis = Connection()
        self.addCleanup(redis.clear)
        redis.set(f"{settings.REDIS_PREFIX}DATETIME_VALUE", PY2_DATETIME_PROTOCOL_0)
        redis.set(f"{settings.REDIS_PREFIX}INT_VALUE", pickle.dumps(42))

        self.migrate()

        self.assertEqual(loads(redis.get(f"{settings.REDIS_PREFIX}DATETIME_VALUE")), datetime(2017, 5, 15, 10, 30))
        self.assertEqual(loads(redis.get(f"{settings.REDIS_PREFIX}INT_VALUE")), 42)
