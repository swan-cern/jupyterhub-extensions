#!/bin/bash

# Author: Enric Tejedor 2015
# Copyright CERN

CULLING_PERIOD=3600 # seconds
CONTAINER_TIMEOUT=86400 # seconds

pidculler=`ps -Txa | grep cull_idle_servers.py | head -1 | awk '{print $1}'`
kill -9 $pidculler

JPY_API_TOKEN=`jupyterhub token` python3 cull_idle_servers.py --url=http://128.142.195.52:8081/hub --cull_every=$CULLING_PERIOD --timeout=$CONTAINER_TIMEOUT
