###############################################################
# -*- coding: utf-8 -*-
__author__ = 'Andrew Leech'

import os
import yaml
class dotdict(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.yaml')

## Startup
assert os.path.exists(CONFIG_FILE), "Please create config file in format similar to example: " + CONFIG_FILE

with open(CONFIG_FILE, 'r') as configfile:
    config = yaml.load(configfile)

assert config.get('kodi_github_repo'), "Incorrect format of config file, missing kodi_github_repo section"
config = config.get('kodi_github_repo')

assert isinstance(config.get('repositories'), list) and len(config.get('repositories')), "Missing repositories from config"

## Defaults
github_personal_access_token = None

repositories = []
debug_server = dotdict(
	port = 8000,
	)

redis_server = dotdict(
    host='localhost',
    port=6379,
    db=0)


## Set up shared static config for app
redis_url = "redis://{host}:{port}/{db}".format(**redis_server)
class redis_keys(object):
    details    = "kodi_github_repo__details"
    addons_xml = "kodi_github_repo__addons_xml"

# Add config.yaml keys directly to module
for key in config:
    val = config[key]
    val = dotdict(val) if isinstance(val, dict) else val
    vars()[key] = val