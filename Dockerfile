FROM gitlab-registry.cern.ch/swan/docker-images/jupyterhub:v3.23
COPY . .
RUN pip install ./SwanSpawner ./SwanHub ./SwanCuller
