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

from flask import Flask, redirect, abort, url_for, render_template, send_from_directory, request
from flask.ext.cache import Cache

import os
import redis
import config
import pprint
import jsonpickle
import github_handler
import semantic_version
from functools import wraps

app = Flask(__name__)

cache = Cache(app,config={'CACHE_TYPE': 'redis',
                          'CACHE_KEY_PREFIX': 'kodi_repo_app',
                          'CACHE_REDIS_URL': config.redis_url
                           })
redisStore = redis.StrictRedis(**config.redis_server)

app.config['PROPAGATE_EXCEPTIONS'] = True

if not app.debug and config.logfile:
    import logging
    from logging.handlers import TimedRotatingFileHandler
    logfile = config.logfile
    if not os.path.isabs(logfile):
        logfile = os.path.abspath(os.path.join(os.path.dirname(__file__), logfile))
    file_handler = TimedRotatingFileHandler(logfile, backupCount=7)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)

    app.logger.addHandler(file_handler)
    app.logger.warn("startup")

def log_exception(exception=Exception, logger=app.logger):
    def deco(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exception as err:
                if logger:
                    logger.exception(err)
                raise
        return wrapper
    return deco

@app.route('/favicon.<ext>')
def favicon(ext):
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.'+ext)

@app.errorhandler(404)
@cache.cached(timeout=0)
@log_exception()
def page_not_found(e):
    app.logger.error("%s : %s" % (e, request.path))
    return render_template('404.html'), 404

@app.route('/')
# @cache.cached(timeout=5*60)
@log_exception()
def home():
    details = jsonpickle.decode(redisStore.get(config.redis_keys.details).decode())
    return render_template('home.html', details=details)

@app.route('/repo/addons.xml')
@cache.cached(timeout=5*60)
@log_exception()
def addons_xml_page():
    addons_xml, addons_xml_md5 = jsonpickle.decode(redisStore.get(config.redis_keys.addons_xml).decode())
    return addons_xml

@app.route('/repo/addons.xml.md5')
@cache.cached(timeout=5*60)
@log_exception()
def addons_xml_md5_page():
    addons_xml, addons_xml_md5 = jsonpickle.decode(redisStore.get(config.redis_keys.addons_xml).decode())
    return addons_xml_md5

@app.route('/repo/<addon_id>')
@cache.cached(timeout=5*60)
@log_exception()
def addon_page(addon_id):
    details = jsonpickle.decode(redisStore.get(config.redis_keys.details).decode())
    if addon_id in details:
        # return render_template('addon.html', repo=details[addon_id])
        repo = details[addon_id]
        url = "https://github.com/{owner}/{reponame}/tree/{newest_tagname}".format(
                owner=repo.owner, reponame=repo.reponame, newest_tagname=repo.newest_tagname)
        return redirect(url)
    else:
        return abort(404)

@app.route('/repo/<addon_id>/<zip_addon_id>-<vers>.zip')
@app.route('/repo/<addon_id>/<zip_addon_id>.zip')
@cache.cached(timeout=5*60)
@log_exception()
def zip_url(addon_id, zip_addon_id, vers=None):
    url = None
    details = jsonpickle.decode(redisStore.get(config.redis_keys.details).decode())
    if (addon_id == zip_addon_id or zip_addon_id is None) and addon_id in details:
        repo_dets = details[zip_addon_id]
        assert isinstance(repo_dets, github_handler.RepoDetail)

        if not vers:
            vers = sorted(repo_dets.downloads.keys(), key=lambda v:semantic_version.Version(v))[-1]

        if vers and vers in repo_dets.downloads:
            url = repo_dets.downloads[vers]

    if url:
        return redirect(url)
    else:
        return abort(404)

if __name__ == '__main__':
    from werkzeug.contrib.profiler import ProfilerMiddleware
    app.config['PROFILE'] = True

    app.wsgi_app = ProfilerMiddleware(app.wsgi_app, restrictions=[30])

    app.run(debug=True, host='0.0.0.0', port=config.debug_server.port)

