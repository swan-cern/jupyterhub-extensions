###
# Remember to authorize the pod where JupyterHub runs to access the API
# of the cluster and to list pods in the namespace
#
# As temporary workaround:
# kubectl create clusterrolebinding add-on-cluster-admin --clusterrole=cluster-admin --serviceaccount=boxed:default
###

# Configuration file for JupyterHub
import os
import socket
from kubespawner.spawner import KubeSpawner as KubeS

### VARIABLES ###

# Get configuration parameters from environment variables

LDAP_URI = os.environ['LDAP_URI']
LDAP_PORT = os.environ['LDAP_PORT']
LDAP_BASE_DN = os.environ['LDAP_BASE_DN']
NAMESPACE = os.environ['PODINFO_NAMESPACE']
NODE_SELECTOR_KEY = os.environ['NODE_SELECTOR_KEY']  # for select the server for swan/JupyterHub
NODE_SELECTOR_VALUE = os.environ['NODE_SELECTOR_VALUE']  # for select the server for swan/JupyterHub
URL_BASE = os.environ['URL_BASE']

BASE_PROJECT_DIR = os.environ['BASE_PROJECT_DIR']
STAGE = os.environ['STAGE']  # DEV or APPS
KubeS.stage = STAGE
KubeS.stage_dir = BASE_PROJECT_DIR + '/' + STAGE

CONFIG_DIR = '/srv/jupyterhub/Config'  # Volume mounted for Config
SWAN_CONFIG_DIR = '/srv/jupyterhub/Config/swan'  # Volume mounted for Config

KubeS.host_config_dir = '/eos/jeodpp/home/users/marlelu/cs3mesh/Config'
KubeS.host_shared_dir = '/mnt/jeoproc/tmp/jupyterhub'
KubeS.config_dir = CONFIG_DIR
KubeS.swan_config_dir = SWAN_CONFIG_DIR
KubeS.service_account = "hubdev"

# c.KubeSpawner.service_account = "hubdev"


# from JeoClasses.mpi import *

c = get_config()

### Configuration for JupyterHub ###
# JupyterHub runtime configuration
jupyterhub_runtime_dir = '/srv/jupyterhub/jupyterhub_data/'
os.makedirs(jupyterhub_runtime_dir, exist_ok=True)
c.JupyterHub.cookie_secret_file = os.path.join(jupyterhub_runtime_dir, 'cookie_secret')
c.JupyterHub.db_url = os.path.join(jupyterhub_runtime_dir, 'jupyterhub.sqlite')

# Resume previous state if the Hub fails
c.JupyterHub.cleanup_proxy = False  # Do not kill the proxy if the hub fails (will return 'Service Unavailable')
c.JupyterHub.cleanup_servers = False  # Do not kill single-user's servers (SQLite DB must be on persistent storage)

# Luca@JRC added for jeodpp. domain
# in order to start from a main domain from a subpath ex.. mydoman.org/here/my/subpath
c.JupyterHub.base_url = URL_BASE

# Logging
c.JupyterHub.log_level = 'DEBUG'
c.Spawner.debug = True
c.JupyterHub.template_paths = ['/srv/jupyterhub/jh_gitlab/templates']
c.JupyterHub.logo_file = '/usr/local/share/jupyterhub/static/swan/logos/Logo512.png'

# Reach the Hub from outside
c.JupyterHub.ip = "0.0.0.0"  # Listen on all IPs for HTTP traffic when in Kubernetes
c.JupyterHub.port = 8000  # You may end up in detecting the wrong IP address due to:
#       - Kubernetes services in front of Pods (headed//headless//clusterIPs)
#       - hostNetwork used by the JupyterHub Pod

c.JupyterHub.cleanup_servers = False
# Use local_home set to true to prevent ca
c.LocalProcessSpawner.debug = True

# Add SWAN look&feellling the script that updates EOS tickets
c.JupyterHub.services = [
    {
        'name': 'cull-idle',
        'admin': True,
        'command': 'swanculler --cull_every=600 --timeout=14400 --disable_hooks=True --cull_users=True'.split(),
    },
    {
        'name': 'notifications',
        'command': 'swannotificationsservice --port 8989'.split(),
        'url': 'http://127.0.0.1:8989'
    }
]

# Reach the Hub from Jupyter containers
# NOTE: The Hub IP must be known and rechable from spawned containers
# 	Leveraging on the FQDN makes the Hub accessible both when the JupyterHub Pod
#	uses the Kubernetes overlay network and the host network
try:
    hub_ip = socket.gethostbyname(socket.getfqdn())
except:
    print("WARNING: Unable to identify iface IP from FQDN")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    hub_ip = s.getsockname()[0]
hub_port = 8080
c.JupyterHub.hub_ip = hub_ip
c.JupyterHub.hub_port = hub_port
c.KubeSpawner.hub_connect_ip = hub_ip
c.KubeSpawner.hub_connect_port = hub_port

c.JupyterHub.allow_named_servers = True
c.JupyterHub.named_server_limit_per_user = 1

# Load the list of users with admin privileges and enable access
admins = set(open(os.path.join(os.path.dirname(__file__), 'adminslist'), 'r').read().splitlines())
c.Authenticator.admin_users = admins
c.JupyterHub.admin_access = True

### User Authentication ###
if (os.environ['AUTH_TYPE'] == "shibboleth"):
    print("Authenticator: Using user-defined authenticator")
    c.JupyterHub.authenticator_class = '%%%SHIBBOLETH_AUTHENTICATOR_CLASS%%%'
    # %%% Additional SHIBBOLETH_AUTHENTICATOR_CLASS parameters here %%% #

elif (os.environ['AUTH_TYPE'] == "local"):
    print("Authenticator: Using LDAP")
    c.JupyterHub.authenticator_class = 'ldapauthenticator.LDAPAuthenticator'
    c.LDAPAuthenticator.server_address = LDAP_URI
    c.LDAPAuthenticator.use_ssl = False
    c.LDAPAuthenticator.server_port = int(LDAP_PORT)
    if (LDAP_URI[0:8] == "ldaps://"):
        c.LDAPAuthenticator.use_ssl = True
    c.LDAPAuthenticator.bind_dn_template = 'uid={username},' + LDAP_BASE_DN

else:
    print("ERROR: Authentication type not specified.")
    print("Cannot start JupyterHub.")

### Configuration for single-user containers ###

def modify_pod_hook(spawner, pod):
    """
    :param spawner: Swan Kubernetes Spawner
    :type spawner: swanspawner.SwanKubeSpawner
    :param pod: default pod definition set by jupyterhub
    :type pod: client.V1Pod

    :returns: dynamically customized pod specification for user session
    :rtype: client.V1Pod
    """

    if hasattr(spawner, "modify_pod_class"):
        if spawner.modify_pod_class in globals():
            spawner.log.info("modify_pod_class is in globals()")
            print(("modify_pod_class in JeoSpawner is set to and is loaded: " + spawner.modify_pod_class))
            pod_hook_handler = globals()[spawner.modify_pod_class](spawner, pod)
            return pod_hook_handler.get_swan_user_pod()
        else:
            spawner.log.warning("class " + spawner.modify_pod_class + " doesn't exist")
    return pod


"""
Configuration for JupyterHub
"""

# Spawn single-user's servers in the Kubernetes cluster
c.JupyterHub.spawner_class = 'jeodppspawner.JeodppKubeSpawner'

if c.JupyterHub.spawner_class == 'jeodppspawner.JeodppKubeSpawner':

    # https://jupyterhub-kubespawner.readthedocs.io/en/latest/spawner.html
    c.JeodppKubeSpawner.modify_pod_hook = modify_pod_hook

    # c.JeodppSpawner.namespace = NAMESPACE
    # c.JeodppSpawner.node_selector = {NODE_SELECTOR_KEY: NODE_SELECTOR_VALUE}  # Where to run user containers

    c.JeodppSpawner.options_form_template = SWAN_CONFIG_DIR + '/jupyterhub_form_template.html'

    c.JeodppSpawner.options_form_per_user = SWAN_CONFIG_DIR

    c.JeodppSpawner.start_timeout = 90

c.Spawner.default_url = '/lab'

c.JeodppSpawner.local_home = True  # $HOME is a volatile scratch space at /scratch/<username>/  Luca@jrc
# c.JeodppSpawner.local_home = False	# $HOME is on EOS
c.JeodppSpawner.volume_mounts = [
    {
        'name': 'eos',
        'mountPath': '/eos:shared',  # Luca@jrc  ## it was /eos/users
    },
    {
        'name': 'user-home',
        'mountPath': '/home/{username}',
    },
    {
        'name': 'scratch',
        'mountPath': '/scratch:shared',
    },
    {
        'name': 'scratch2',
        'mountPath': '/scratch2:shared',
    }
]

c.JeodppSpawner.volumes = [
    {
        'name': 'eos',
        'hostPath': {
            'path': '/eos',
            'type': '',
        }
    },
    {
        'name': 'user-home',
        'hostPath': {
            'path': '/mnt/jeoproc/sharedscratch/user_homes/{username}',
            'type': '',
        }
    },
    {
        'name': 'scratch',
        'hostPath': {
            'path': '/scratch',
            'type': '',
        }
    },
    {
        'name': 'scratch2',
        'hostPath': {
            'path': '/scratch2',
            'type': '',
        }
    }
]
# c.JeodppSpawner.available_cores = ["2", "4"]
# c.JeodppSpawner.available_memory = ["12", "20"]
c.JeodppSpawner.check_cvmfs_status = False  # For now it only checks if available in same place as Jupyterhub.

# c.JeodppSpawner.extra_env = dict(
#     SHARE_CBOX_API_DOMAIN="https://%%%CERNBOXGATEWAY_HOSTNAME%%%",
#     SHARE_CBOX_API_BASE="/cernbox/swanapi/v1",
#     HELP_ENDPOINT="https://raw.githubusercontent.com/swan-cern/help/up2u/"
# )

# local_home equal to true to hide the "always start with this config"
c.SpawnHandlersConfigs.local_home = True
c.SpawnHandlersConfigs.metrics_on = False  # For now the metrics are hardcoded for CERN
c.SpawnHandlersConfigs.spawn_error_message = """SWAN could not start a session for your user, please try again. If the problem persists, please check:
<ul>
    <li>Do you have a CERNBox account? If not, click <a href="https://%%%CERNBOXGATEWAY_HOSTNAME%%%" target="_blank">here</a>.</li>
    <li>Check with the service manager that SWAN is running properly.</li>
</ul>"""
