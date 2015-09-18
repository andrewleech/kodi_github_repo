###############################################################
# -*- coding: utf-8 -*-
__author__ = "Andrew Leech"

import os
import re
import redis
import base64
import config
import zipfile
import hashlib
import logging
import requests
import tempfile
import subprocess
import jsonpickle
import semantic_version
from collections import OrderedDict
from distutils.dir_util import remove_tree
from github3 import login, GitHubError, utils

_log = logging.getLogger(__name__)

class RepoDetail(object):
    """
    Basic structure to hold all desired repo details in cache
    """
    def __init__(self, repo=None):
        # These hold binary github objects
        self.repo = repo
        self.tags = {}
        self.releases = {}

        # These hold simple information
        self.reponame = repo.name if repo else ""
        self.description = repo.description if repo else ""
        self.homepage = repo.homepage if repo else ""
        self.owner = repo.owner if repo else ""
        self.tagnames = {}
        self.downloads = {}
        self.newest_version = None
        self.newest_zip = None
        self.newest_tagname = None
        self.addon_xml = None

    def __getstate__(self):
        d = self.__dict__
        del d['repo']
        del d['tags']
        del d['releases']
        return d

    def __setstate__(self, d):
        self.__dict__.update(d)

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

def vers_from_tag(tagname):
    tag_vers = None
    tag_vers_match = re.findall(r'(\d+\.\d+\.\d+.*?) ?', tagname)
    if tag_vers_match:
        tag_vers = tag_vers_match[0]
    return tag_vers

def repo_tags(repo):
    """
    Parses all git tags on the repo for semantic version numbers
    """
    tags = {}
    for tag in repo.iter_tags():
        name = tag.name
        tag_vers = vers_from_tag(name)
        if tag_vers:
            tags[tag_vers] = tag

    return tags

def repo_releases(repo, tags):
    """
    finds matching release for each tag. Creates one if not available
    """
    releases = {vers_from_tag(rel.tag_name) : rel for rel in repo.iter_releases()}
    # for release in repo.iter_releases():
    #     name = release.tag_name
    for vers, tag in tags.items():
        if vers not in releases:
            # create release
            _log.warning('Generating new release for %s:%s' % (repo.name, tag.name))
            release = repo.create_release(tag.name)
            releases[vers] = release
    return releases

def repo_downloads(repo, releases, tags):
    """
    finds matching download for each release. Creates one if not available
    """
    downloads = {}
    # for release in repo.iter_releases():
    #     name = release.tag_name
    for vers, release in releases.items():
        download_url = None
        download_asset = None
        download_asset_name = repo.name + ".zip"
        for asset in release.iter_assets():
            if asset.name == download_asset_name:
                download_asset = asset
                break

        if not download_asset:
            # Create download... this will take a while
            _log.warning('Generating new release download zip for %s:%s' % (repo.name, vers))
            zip_url = tags[vers].zipball_url
            temp_dir = tempfile.mkdtemp()
            try:
                zip_dlfile = os.path.join(temp_dir, download_asset_name)
                _log.warning('downloading')
                download(zip_url, zip_dlfile)
                if os.path.exists(zip_dlfile):
                    _log.warning('extracting')
                    # outdir = extract(zip_dlfile)
                    outdir = os.path.splitext(zip_dlfile)[0]
                    subprocess.check_output(['/usr/bin/unzip', zip_dlfile, '-d', outdir])
                    contents = os.listdir(outdir)
                    _log.warning('renaming')
                    if len(contents) == 1 and os.path.isdir(os.path.join(outdir,contents[0])):
                        innerdir = contents[0]
                        newdir = os.path.join(outdir,innerdir)
                        if innerdir != repo.name:
                            os.rename(newdir, os.path.join(outdir,repo.name))
                        outdir = os.path.join(outdir,repo.name)
                    os.rename(zip_dlfile, zip_dlfile+".dl")
                    _log.warning('zipping')
                    zipdir(dirPath=outdir, zipFilePath=zip_dlfile, includeDirInZip=True, excludeDotFiles=True)

                    if os.path.exists(zip_dlfile):
                        with open(zip_dlfile, 'rb') as assetfile:
                            _log.warning('uploading')
                            download_asset = release.upload_asset(
                                                    content_type='application/zip, application/octet-stream',
                                                    name=download_asset_name,
                                                    asset=assetfile)
                        _log.warning('Finished new release download zip for %s:%s' % (repo.name, vers))
            except:
                _log.exception("zip_url: %s"%zip_url)
            finally:
                remove_tree(temp_dir)

        if download_asset:
            download_url = download_asset.browser_download_url

        downloads[vers] = download_url
    return downloads

def newest_repo_version(tags):
    newest_version = None
    newest_semvers = None
    for entry in tags.keys():
        try:
            semvers = semantic_version.Version(entry)
            if newest_semvers is None or (semvers > newest_semvers and not semvers.prerelease):
                newest_version = entry
                newest_semvers = semvers
        except ValueError as ex:
            _log.exception("invalid tag version (%s) from %s" % (entry, tags[entry][1]))
    return newest_version, tags[newest_version]

def kodi_repos(repos):
    """
    For all repositories in provided list, construct a RepoDetail container with details we need
    """
    
    # Get list of repository objects and wrap in RepoDetail class
    details = OrderedDict([
          (repo.name, RepoDetail(repo)) for repo in sorted(repos, key=lambda r:r.name)
    ])
    
    for repo_det in details.values():
        # Get latest version
        tags = repo_tags(repo_det.repo)
        repo_det.tags = tags
        repo_det.tagnames = {vers:tag.name for vers,tag in tags.items()}
        
        releases = repo_releases(repo_det.repo, tags)
        repo_det.releases = releases

        downloads = repo_downloads(repo_det.repo, releases, tags)
        repo_det.downloads = downloads

        version, newest_tag = newest_repo_version(tags)
        repo_det.newest_version = version
        repo_det.newest_tagname = newest_tag.name

        # Grab a copy of addon.xml from the latest version
        addon_xml_handle = repo_det.repo.contents('addon.xml',repo_det.newest_tagname)
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
    
    # Don't store reference to repo object to reduce serialiser load
    for repo_det in _details.values():
        repo_det.repo = None
    
    _redisStore.set(config.redis_keys.details, jsonpickle.encode(_details))
    _redisStore.set(config.redis_keys.addons_xml, jsonpickle.encode(_addons_xml))

## The functions below are used for creating the assets for a release

def download(url, path=''):
    """Download the data for this asset.
    :param path: (optional), path where the file should be saved
        to, default is the filename provided in the headers and will be
        written in the current directory.
        it can take a file-like object as well
    :type path: str, file
    :returns: name of the file, if successful otherwise ``None``
    :rtype: str
    """
    # headers = {
    #     'Accept': 'application/zip, application/octet-stream'
    #     }
    headers = {}
    resp = None
    status_code = 302
    while status_code == 302:
        resp = requests.get(url, allow_redirects=False, stream=True, headers=headers)
        status_code = resp.status_code
        if status_code == 302:
            url = resp.headers['location']
            # Amazon S3 will reject the redirected request unless we omit
            # certain request headers
            if 's3' in resp.headers['location']:
                headers.update({'Content-Type': None})

    if resp and resp_check(resp, 200, 404):
        return utils.stream_response_to_file(resp, path)
    return None


def resp_check(response, true_code, false_code):
    if response is not None:
        status_code = response.status_code
        if status_code == true_code:
            return True
        if status_code != false_code and status_code >= 400:
            response.raise_for_status()
    return False

## This is failing for unicode errors with some zip's
## https://bugs.python.org/issue20329
# def extract(filename):
#     folder, extension = os.path.splitext(filename)
#     if extension.endswith('zip'):
#         import zipfile
#         if os.path.exists(folder):
#             remove_tree(folder)
#         if not os.path.exists(folder):
#             os.makedirs(folder)
#         zip = zipfile.ZipFile(filename, 'r')
#         zip.extractall(folder)
#     return folder

def zipdir(dirPath=None, zipFilePath=None, includeDirInZip=True, excludeDotFiles=True):
    """Create a zip archive from a directory.
    
    Note that this function is designed to put files in the zip archive with
    either no parent directory or just one parent directory, so it will trim any
    leading directories in the filesystem paths and not include them inside the
    zip archive paths. This is generally the case when you want to just take a
    directory and make it into a zip file that can be extracted in different
    locations. 
    
    Keyword arguments:
    
    dirPath -- string path to the directory to archive. This is the only
    required argument. It can be absolute or relative, but only one or zero
    leading directories will be included in the zip archive.
    zipFilePath -- string path to the output zip file. This can be an absolute
    or relative path. If the zip file already exists, it will be updated. If
    not, it will be created. If you want to replace it from scratch, delete it
    prior to calling this function. (default is computed as dirPath + ".zip")
    includeDirInZip -- boolean indicating whether the top level directory should
    be included in the archive or omitted. (default True)
"""
    if not zipFilePath:
        zipFilePath = dirPath + ".zip"
    if not os.path.isdir(dirPath):
        raise OSError("dirPath argument must point to a directory. "
            "'%s' does not." % dirPath)
    parentDir, dirToZip = os.path.split(dirPath)
    #Little nested function to prepare the proper archive path
    def trimPath(path):
        archivePath = path.replace(parentDir, "", 1)
        if parentDir:
            archivePath = archivePath.replace(os.path.sep, "", 1)
        if not includeDirInZip:
            archivePath = archivePath.replace(dirToZip + os.path.sep, "", 1)
        return os.path.normcase(archivePath)
        
    outFile = zipfile.ZipFile(zipFilePath, "w",
        compression=zipfile.ZIP_DEFLATED)
    for (archiveDirPath, dirNames, fileNames) in os.walk(dirPath):
        if excludeDotFiles:
            fileNames = [f for f in fileNames if not f[0] == '.']
            dirNames[:] = [d for d in dirNames if not d[0] == '.']
        for fileName in fileNames:
            filePath = os.path.join(archiveDirPath, fileName)
            outFile.write(filePath, trimPath(filePath))
        #Make sure we get empty directories as well
        if not fileNames and not dirNames:
            zipInfo = zipfile.ZipInfo(trimPath(archiveDirPath) + "/")
            #some web sites suggest doing
            #zipInfo.external_attr = 16
            #or
            #zipInfo.external_attr = 48
            #Here to allow for inserting an empty directory.  Still TBD/TODO.
            outFile.writestr(zipInfo, "")
    outFile.close()

if __name__ == '__main__':
    import pprint
    logging.basicConfig(format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                        datefmt='%Y%m%d %H:%M',
                        level=logging.INFO)
    
    repos = repositories()
    details = kodi_repos(repos)
    pprint.pprint(details)
    print(addons_xml(details))
