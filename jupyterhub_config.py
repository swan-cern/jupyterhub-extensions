
c = get_config()

# The docker instances need access to the Hub, so the default loopback port doesn't work
from jupyter_client.localinterfaces import public_ips
c.JupyterHub.hub_ip = public_ips()[0]

# Authenticator
c.Authenticator.admin_users = {'notebook'}
c.JupyterHub.authenticator_class = 'ssoauthenticator.SSOAuthenticator'

# Spawner
c.JupyterHub.spawner_class = 'cernspawner.CERNSpawner'
c.CERNSpawner.container_image = "cernphsft/systemuser"
c.SystemUserSpawner.read_only_volumes = { '/cvmfs':'/cvmfs' }
c.SystemUserSpawner.volumes = { '/eos' : '/eos'}
c.SystemUserSpawner.options_form = """
<label for="LCG-rel">LCG release</label>
<select name="LCG-rel">
  <option value="82rootaas6" selected>82 ROOTaaS6</option>
</select>
<label for="platform">Platform</label>
<select name="platform">
  <option value="x86_64-slc6-gcc49-opt" selected>x86_64 SLC6 GCC4.9 Opt</option>
</select>
""" 
