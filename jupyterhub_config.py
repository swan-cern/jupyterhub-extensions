c = get_config()

# The docker instances need access to the Hub, so the default loopback port doesn't work:
from jupyter_client.localinterfaces import public_ips
c.JupyterHub.hub_ip = public_ips()[0]
#c.JupyterHub.port = 4443

# Authenticator
c.Authenticator.admin_users = {'jhadmin'}
c.JupyterHub.authenticator_class = 'ssoauthenticator.SSOAuthenticator'

# Spawner
c.JupyterHub.spawner_class = 'cernspawner.CERNSpawner'
c.CERNSpawner.container_image = "cernphsft/systemuser"
c.CERNSpawner.read_only_volumes = { '/cvmfs':'/cvmfs' }
c.CERNSpawner.volumes = { '/eos' : '/eos'}
c.CERNSpawner.auth_script  = '/root/eos-fuse.sh'

c.CERNSpawner.options_form = """
<label for="LCG-rel">LCG release</label>
<select name="LCG-rel">
  <option value="82rootaas6" selected>82 ROOTaaS6</option>
</select>
<label for="platform">Platform</label>
<select name="platform">
  <option value="x86_64-slc6-gcc49-opt" selected>x86_64-slc6-gcc49-opt</option>
</select>
<label for="resource">Resource for the container (Demo)</label>
<select name="resource">
  <option value="teslak80" selected>nVidia Tesla K80</option>
  <option value="100nodesSparkCluster" selected>100 Nodes Spark Cluster</option>
  <option value="20nodesSparkCluster" selected>20 Nodes Spark Cluster</option>
  <option value="10nodesSparkCluster" selected>10 Nodes Spark Cluster</option>
</select>
"""
