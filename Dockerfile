FROM gitlab-registry.cern.ch/swan/docker-images/jupyterhub:v3.10

COPY ./SwanSpawner /tmp/SwanSpawner
COPY ./SwanHub /tmp/SwanHub

RUN pip install /tmp/SwanSpawner && \
    pip install /tmp/SwanHub && \
    rm -rf /tmp/SwanSpawner /tmp/SwanHub

RUN ln -sf /usr/local/bin/swanhub /usr/local/bin/jupyterhub
