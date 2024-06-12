#!/bin/bash

# Wrap the call of configurable-http-proxy to set the max header size.
# Remove the first option (--ip) to allow the proxy to listen on all the interfaces.
node --max-http-header-size=16000 /usr/bin/configurable-http-proxy ${@:2}