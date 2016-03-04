#!/bin/bash

# Author: Enric Tejedor 2015
# Copyright CERN

# This script restarts the jupyterhub server properly
# o Kills the server
# o Kills the proxy
# o Kills the containers
# o Restarts with the proper environment variables set

echo "Restarting JupyterHub"

echo "Removing all containers..."
docker rm -f $(docker ps -a -q)

echo "Killing the current JupyterHub processes..."
pidhub=`ps -Txa | grep /usr/bin/jupyterhub | grep -v grep | head -1 | awk '{print $1}'`
pidproxy=`ps -Txa | grep configurable-http-proxy | grep -v grep | head -1 | awk '{print $1}'`
kill -9 $pidhub
kill -9 $pidproxy

echo "Starting JupyterHub..."
AUTHUSERS=/root/allowedUsers.txt nohup jupyterhub --config /srv/jupyterhub/jupyterhub_config.py > /srv/jupyterhub/jh.out &

echo "Restarting finished!"

