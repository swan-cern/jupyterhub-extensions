c = get_config()

# The docker instances need access to the Hub, so the default loopback port doesn't work:
from jupyter_client.localinterfaces import public_ips
c.JupyterHub.hub_ip = public_ips()[0]

# Authenticator
c.JupyterHub.authenticator_class = 'ssoauthenticator.SSOAuthenticator'
c.SSOAuthenticator.admin_users = {'dpiparo', 'etejedor'}
#c.SSOAuthenticator.accepted_egroup = 'dmaas-test-users'

# Slow spawn warning timeout (redirect to pending page)
c.JupyterHub.tornado_settings = {
    'slow_spawn_timeout': 10
}

# Spawner
c.JupyterHub.spawner_class = 'cernspawner.CERNSpawner'
c.CERNSpawner.container_image = "cernphsft/systemuser"
c.CERNSpawner.read_only_volumes = { '/cvmfs':'/cvmfs' }
c.CERNSpawner.volumes = { '/eos' : '/eos'}
c.CERNSpawner.auth_script  = '/root/eos-fuse.sh'
c.CERNSpawner.eos_path_prefix  = '/eos/scratch/user'

# Spawner.http_timeout - https://jupyterhub.readthedocs.io/en/stable/api/spawner.html#jupyterhub.spawner.Spawner.http_timeout
c.SwanSpawner.http_timeout = 30

# Spawner.start_timeout - https://jupyterhub.readthedocs.io/en/stable/api/spawner.html#jupyterhub.spawner.Spawner.start_timeout
#c.SwanSpawner.start_timeout = 60

c.SwanSpawner.options_form_config = 'options_form_config.json'
