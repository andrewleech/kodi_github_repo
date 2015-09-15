###############################################################
# -*- coding: utf-8 -*-
__author__ = "Andrew Leech"

import re
import redis
import base64
import config
import hashlib
import logging
import jsonpickle
import semantic_version
from github import Github

_log = logging.getLogger(__name__)

class repo_details(object):
    """
    Basic structure to hold all desired repo details in cache
    """
    def __init__(self, repo=None):
        self.repo = repo
        self.all_versions = {}
        self.newest_version = None
        self.newest_zip = None
        self.newest_tagname = None
        self.addon_xml = None

def repositories():
    """
    Gets list of repository objects for each configured repository name
    """
    _log.info("Getting configured repositories details...")
    _repos = []
    _github = Github()
    url_re = re.compile('github\.com/(.*?)/(.*?)(?:\.git$|$)')
    for repo_url in config.repositories:
        repo_parts = re.findall(url_re, repo_url)
        if repo_parts:
            user, repo = repo_parts[0][0:2]
            github_repo = _github.get_user(user).get_repo(repo)
            _repos.append(github_repo)
    return _repos

def repo_versions(repo):
    """
    Parses all git tags on the repo for semantic version numbera
    """
    versions = {}
    for tag in repo.get_tags():
        tag_vers_match = re.findall(r'(\d+.\d+.\d+.*?) ?', tag.name)
        if tag_vers_match:
            tag_vers = tag_vers_match[0]
            versions[tag_vers] = (tag.zipball_url, tag.name)
    return versions

def newest_repo_version(versions):
    newest_version = sorted(versions.keys(), key = lambda v:semantic_version.Version(v))[-1]
    return newest_version, versions[newest_version]

def kodi_repos(repos):
    """
    For all repositories in provided list, construct a repo_details container with details we need
    """
    
    # Get list of repository objects and wrap in repo_details class
    details = {
        repo.name:repo_details(repo) for repo in repos
    }
    
    for repo_det in details.values():
        # Get latest version
        versions = repo_versions(repo_det.repo)
        repo_det.all_versions = versions
        version, (newest_zip, newest_tagname) = newest_repo_version(versions)
        repo_det.newest_version = version
        repo_det.newest_zip = newest_zip
        repo_det.newest_tagname = newest_tagname

        # Grab a copy of addon.xml from the latest version
        addon_xml_handle = repo_det.repo.get_file_contents('addon.xml',newest_tagname)
        if addon_xml_handle.encoding == 'base64':
            addon_xml = base64.b64decode(addon_xml_handle.content)
        else:
            addon_xml = addon_xml_handle.content
            _log.warning('Unexpected encoding (%s) on file: %s' % (addon_xml_handle.encoding, addon_xml_handle.name))
        repo_det.addon_xml = addon_xml

    return details

def addons_xml(details):
    """
    Generate kodi repo addons.xml with md5 hash
    """
    # repo addons header
    _addons_xml = u"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n<addons>\n"
    
    # add addon.xml from each addon verbatim
    for repo_det in details.values():
        xml = repo_det.addon_xml.rstrip()
        if isinstance(xml, bytes):
            xml = xml.decode()
        if xml.startswith('<?xml'):
            xml = xml[xml.index('\n'):]
        _addons_xml += xml + u"\n\n"
    
    # clean and add closing tag
    _addons_xml = _addons_xml.strip() + u"\n</addons>\n"
    _addons_xml_md5 = hashlib.md5(_addons_xml.encode()).digest()
    return _addons_xml, _addons_xml_md5
        
def update_kodi_repos_redis():
    """
    Generate details of all repos and the addons.xml then store them to redis cache
    """
    _redisStore = redis.StrictRedis(**config.redis_server)
    _details = kodi_repos(repositories())
    _addons_xml = addons_xml(_details)
    _redisStore.set(config.redis_keys.details, jsonpickle.encode(_details))
    _redisStore.set(config.redis_keys.addons_xml, jsonpickle.encode(_addons_xml))

if __name__ == '__main__':
    import pprint
    logging.basicConfig(format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                        datefmt='%Y%m%d %H:%M',
                        level=logging.INFO)
    
    repos = repositories()
    details = kodi_repos(repos)
    pprint.pprint(details)
    print(addons_xml(details))
