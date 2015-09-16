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
from github3 import login, GitHubError

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
    _github = login(token=config.github_personal_access_token)

    url_re = re.compile('github\.com/(.*?)/(.*?)(?:\.git$|$)')
    for repo_url in config.repositories:
        repo_parts = re.findall(url_re, repo_url)
        if repo_parts:
            user, repo = repo_parts[0][0:2]
            try:
                github_repo = _github.repository(user,repo)
            except GitHubError:
                raise Exception("Github error: %s/%s"%(user, repo))
            _repos.append(github_repo)
    return _repos

def repo_versions(repo):
    """
    Parses all git tags on the repo for semantic version numbera
    """
    versions = {}
    # for release in repo.iter_releases():
    #     name = release.tag_name
    for tag in repo.iter_tags():
        name = tag.name
        tag_vers_match = re.findall(r'(\d+\.\d+\.\d+.*?) ?', name)
        if tag_vers_match:
            tag_vers = tag_vers_match[0]

            ## The API is annoying as far as zipfiles are concerned...
            # download_asset = None
            # download_asset_name = repo.name + ".zip"
            # download_url = None
            # for asset in release.iter_assets():
            #     if asset.name.endswith('.zip'):
            #         download_asset = asset
            #     if asset.name == download_asset_name:
            #         break
            # if download_asset:
            #     if download_asset.name != download_asset_name:
            #         # fix name
            #         pass
            #     download_url = download_asset.download_url

            ## The auto-generated zip link on a github created release page (as seen in browser) gives me a zip with
            ## the correct name, whereas the api only ever seems to give me one with the username and sha in the name.

            ## just throw a hammer at it, and hope it keeps giving me the goods
            # download_url = "https://codeload.github.com/{owner}/{repo}/zip/{tag}".format(owner=repo.owner, repo=repo.name, tag=name)
            download_url = "https://github.com/{owner}/{repo}/archive/{tag}.zip".format(owner=repo.owner, repo=repo.name, tag=name)


            versions[tag_vers] = (download_url, name)

    return versions

def newest_repo_version(versions):
    newest_version = None
    newest_semvers = None
    for entry in versions.keys():
        try:
            semvers = semantic_version.Version(entry)
            if newest_semvers is None or (semvers > newest_semvers and not semvers.prerelease):
                newest_version = entry
                newest_semvers = semvers
        except ValueError as ex:
            _log.exception("invalid tag version (%s) from %s" % (entry, versions[entry][1]))
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
        addon_xml_handle = repo_det.repo.contents('addon.xml',newest_tagname)
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
