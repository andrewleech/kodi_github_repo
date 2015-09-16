###############################################################
# -*- coding: utf-8 -*-
#!/usr/bin/env python

__author__ = "Andrew Leech"
__copyright__ = "Copyright 2015, alelec"
__license__ = "GPL"
__version__ = "1.0.1"
__maintainer__ = "Andrew Leech"
__email__ = "andrew@alelec.net"
__status__ = "Development"

import config
import github_handler
from celery import Celery
from datetime import timedelta

app = Celery('kodi_repo_task', 
             broker=config.redis_url,
             backend=config.redis_url,
             )

app.conf.update(
    CELERY_ACCEPT_CONTENT = ['json'],
    CELERY_TASK_SERIALIZER = 'json',
    CELERY_RESULT_SERIALIZER = 'json',

    CELERYBEAT_SCHEDULE = {
        'update_kodi_repos_details': {
            'task': 'kodi_repo_task.periodic_update_kodi_repos_details',
            'schedule': timedelta(minutes=15),
        },
    }
)

# @app.on_after_configure.connect
# def setup_periodic_tasks(sender, **kwargs):
#     # Calls test('hello') every 10 seconds.
#     sender.add_periodic_task(15*60, periodic_update_kodi_repos_details.s(), name='update_kodi_repos_details')

#     # # Executes every Monday morning at 7:30 A.M
#     # sender.add_periodic_task(
#     #     crontab(hour=7, minute=30, day_of_week=1),
#     #     test.s('Happy Mondays!'),

@app.task
def periodic_update_kodi_repos_details():
    return github_handler.update_kodi_repos_redis()


# Update cached details once at startup
github_handler.update_kodi_repos_redis()
