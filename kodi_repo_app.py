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

from flask import Flask, redirect, abort
from flask.ext.cache import Cache

import redis
import config
import jsonpickle
import github_handler
import semantic_version

app = Flask(__name__)
#cache = Cache(app,config={'CACHE_TYPE': 'simple'})
cache = Cache(app,config={'CACHE_TYPE': 'redis',
                          'CACHE_KEY_PREFIX': 'kodi_repo_app',
                          'CACHE_REDIS_URL': config.redis_url
                           })
redisStore = redis.StrictRedis(**config.redis_server)

@app.route('/')
def main_page():
    return 'TBD'

@app.route('/repo/addons.xml')
@cache.cached(timeout=1*60)
def addons_xml_page():
    addons_xml, addons_xml_md5 = jsonpickle.decode(redisStore.get(config.redis_keys.addons_xml).decode())
    return addons_xml

@app.route('/repo/addons.xml.md5')
@cache.cached(timeout=1*60)
def addons_xml_md5_page():
    addons_xml, addons_xml_md5 = jsonpickle.decode(redisStore.get(config.redis_keys.addons_xml).decode())
    return addons_xml_md5

@app.route('/repo/<addon_id>/<zip_addon_id>-<vers>.zip')
def zip_url(addon_id, zip_addon_id, vers):
    url = None
    details = jsonpickle.decode(redisStore.get(config.redis_keys.details).decode())
    if zip_addon_id in details:
        repo_dets = details[zip_addon_id]
        assert isinstance(repo_dets, github_handler.repo_details)
        if vers in repo_dets.all_versions:
            url, tagname = repo_dets.all_versions[vers]
    if url:
        return redirect(url)
    else:
        return abort(404)

if __name__ == '__main__':
    from werkzeug.contrib.profiler import ProfilerMiddleware
    app.config['PROFILE'] = True
    app.wsgi_app = ProfilerMiddleware(app.wsgi_app, restrictions=[30])
    app.run(debug=True, host='0.0.0.0', port=config.debug_server.port)

