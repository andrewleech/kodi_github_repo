# kodi_github_repo
Kodi repository flask webapp that dynamically serves addons from github repos

All addons must be hosted on github in a flat structure such that a direct zip download will create a normal kodi module zip.
This seems to be the most common way for addons to be on github anyway, so should rarely be an issue.
Then just list the module's github url in config.py

When a new version of an addon is ready simply git tag the commit with a semantic version number, eg. v1.1.0

The webapp will check for updated versions in the background and serve the latest of each dynamically.

To install (on ubuntu-ish linux with upstart), choose where you'll store the program on your system, perhaps in home dir, or in var.
I'll call it /path/to/kodi_repo, replace this below with your own desired location
```
apt-get install nginx redis python3 python3-pip
KODI_REPO=/path/to/kodi_repo

mkdir - $KODI_REPO/run
cd $KODI_REPO
git clone https://github.com/andrewleech/kodi_github_repo.git
pip3 install virtualenv
python3 virtualenv virtualenv
source virtualenv/bin/activate
pip3 install --requirement kodi_github_repo/requirements.txt
## System startup scripts
sudo cp kodi_github_repo/upstart_scripts/* /etc/init/
## nginx hosting script
sudo cp kodi_github_repo/nginx_scripts/kodi_github_repo.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/kodi_github_repo.conf /etc/nginx/sites-enabled/kodi_github_repo.conf
```

Then update the three system config files:
- /etc/init/kodi_repo_uwsgi.conf
- /etc/init/kodi_repo_celery.conf
- /etc/nginx/sites-enabled/kodi_github_repo.conf
replacing /path/to/kodi_repo as needed and setting up the virtualhost in nginx conf to suit your server.

```
sudo service nginx start
sudo service redis start
sudo service kodi_repo_celery start
sudo service kodi_repo_uwsgi start
```
and it should all be running!

You'll want a repository addon to point towards your new repo, something like: https://github.com/andrewleech/repository.alelec