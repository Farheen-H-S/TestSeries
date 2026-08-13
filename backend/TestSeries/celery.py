import os
import redis.connection
from celery import Celery

# Compatibility patch for Redis 5 server with redis-py 5.x+:
# redis-py 5.0+ defaults to RESP3 (sending 'HELLO 3' command), which Redis Server 5 does not support.
# Force protocol=2 (RESP2) and disable maintenance notifications to maintain Redis 5 compatibility.
_orig_redis_conn_init = redis.connection.Connection.__init__
def _redis_conn_init_resp2(self, *args, **kwargs):
    kwargs['protocol'] = 2
    kwargs['maint_notifications_config'] = None
    _orig_redis_conn_init(self, *args, **kwargs)
redis.connection.Connection.__init__ = _redis_conn_init_resp2

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TestSeries.settings')

app = Celery('TestSeries')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()
