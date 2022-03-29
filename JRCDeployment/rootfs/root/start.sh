#!/bin/bash 
#set -o errexit	# Bail out on all errors immediately

echo "---${THIS_CONTAINER}---"

case $DEPLOYMENT_TYPE in
  "kubernetes")
    # Print PodInfo
    echo ""
    echo "%%%--- PodInfo ---%%%"
    echo "Pod namespace: ${PODINFO_NAMESPACE}"
    echo "Pod name: ${PODINFO_NAME}"
    echo "Pod IP: ${PODINFO_IP}"
    echo "Node name (of the host where the pod is running): ${PODINFO_NODE_NAME}" 
    echo "Node IP (of the host where the pod is running): ${PODINFO_NODE_IP}"

    echo "Deploying with configuration for Kubernetes..."
    cp /root/jupyterhub_config/kubernetes.py /srv/jupyterhub/jupyterhub_config.py

    echo "Enabling crond for logrotation..."
    mv /etc/supervisord.d/crond.noload /etc/supervisord.d/crond.ini

    echo "Downloading single-user image: $CONTAINER_IMAGE ..."
    docker pull $CONTAINER_IMAGE

    echo "Creating internal Docker network: $DOCKER_NETWORK_NAME ..."
    docker network inspect $DOCKER_NETWORK_NAME > /dev/null 2>&1 || docker network create $DOCKER_NETWORK_NAME
    ;;

  ###
  "kubespawner")
    # Print PodInfo
    echo ""
    echo "%%%--- PodInfo ---%%%"
    echo "Pod namespace: ${PODINFO_NAMESPACE}"
    echo "Pod name: ${PODINFO_NAME}"
    echo "Pod IP: ${PODINFO_IP}"
    echo "Node name (of the host where the pod is running): ${PODINFO_NODE_NAME}" 
    echo "Node IP (of the host where the pod is running): ${PODINFO_NODE_IP}"

    echo "Deploying with configuration for KubeSpawner..."
    cp /root/jupyterhub_config/kubespawner.py /srv/jupyterhub/jupyterhub_config.py

    echo "Enabling crond for logrotation..."
    mv /etc/supervisord.d/crond.noload /etc/supervisord.d/crond.ini
    ;;

  ###
  "compose")
    echo "Deploying with configuration for Docker Compose..."

    # Eventually override the certificates with the ones available in certs/boxed.{key,crt}
    if [[ -f "$HOST_FOLDER"/certs/boxed.crt && -f "$HOST_FOLDER"/certs/boxed.key ]]; then
      echo 'Replacing default certificate for HTTPS...'
      /bin/cp "$HOST_FOLDER"/certs/boxed.crt /etc/boxed/certs/boxed.crt
      /bin/cp "$HOST_FOLDER"/certs/boxed.key /etc/boxed/certs/boxed.key
    fi

    cp /root/jupyterhub_config/docker.py /srv/jupyterhub/jupyterhub_config.py
    ;;
  *)
    echo "ERROR: Deployment context is not defined."
    echo "Cannot continue."
    exit -1
esac

echo "Configuring runtime parameters..."
# Configuration to connect to LDAP
sed -i "s|%%%LDAP_URI%%%|${LDAP_URI}|" /etc/sssd/sssd.conf
sed -i "s|%%%LDAP_BASE_DN%%%|${LDAP_BASE_DN}|" /etc/sssd/sssd.conf
sed -i "s|%%%LDAP_BIND_DN%%%|${LDAP_BIND_DN}|" /etc/sssd/sssd.conf
sed -i "s|%%%LDAP_BIND_PASSWORD%%%|${LDAP_BIND_PASSWORD}|" /etc/sssd/sssd.conf
# Configure httpd proxy with correct ports and hostname
echo "CONFIG: HTTP port is ${HTTP_PORT}"
echo "CONFIG: HTTPS port is ${HTTPS_PORT}"
echo "CONFIG: Hostname is ${HOSTNAME}"
# 1. Traffic on HTTPS port
sed "s/%%%HTTPS_PORT%%%/${HTTPS_PORT}/" /root/httpd_config/jupyterhub_ssl.conf.template > /etc/httpd/conf.d/jupyterhub_ssl.conf
# 2. Traffic on HTTP port for redirection to HTTPS
sed -e "s/%%%HTTP_PORT%%%/${HTTP_PORT}/
s/%%%HTTPS_PORT%%%/${HTTPS_PORT}/
s/%%%HOSTNAME%%%/${HOSTNAME}/" /root/httpd_config/jupyterhub_plain.conf.template > /etc/httpd/conf.d/jupyterhub_plain.conf
# Configure Jupyter extensions
sed -i "s|%%%CERNBOXGATEWAY_HOSTNAME%%%|${CERNBOXGATEWAY_HOSTNAME}|" /srv/jupyterhub/jupyterhub_config.py

## Configure the spawner form # @luca removed after using Userform
#SPAWNER_FORM="jeodpp-jhub"
#case $SPAWNER_FORM in
#  "complete")
#    ln -s /srv/jupyterhub/jupyterhub_form.complete.html /srv/jupyterhub/jupyterhub_form.html
#    echo "CONFIG: Using complete spawner form"
#    ;;
#  "simple")
#    ln -s /srv/jupyterhub/jupyterhub_form.simple.html /srv/jupyterhub/jupyterhub_form.html
#    echo "CONFIG: Using simple spawner form"
#    ;;
#  "jeodpp-jhub")
#    ln -s /srv/jupyterhub/jupyterhub_form.jeodpp-jhub.html /srv/jupyterhub/jupyterhub_form.html
#    echo "CONFIG: Using JEODPP jhub spawner form"
#    ;;
#  "none")
#    #TODO: To be implemented
#    echo "CONFIG: No spawner form used"
#    echo "ERROR: TO BE IMPLEMENTED"
#    echo "ERROR: Defaulting to complete spawner form for now..."
#    ln -s /srv/jupyterhub/jupyterhub_form.complete.html /srv/jupyterhub/jupyterhub_form.html
#    ;;
#  *)
#    echo "WARNING: Jupyterhub spawner form type unknown or unspecified. Defaulting to complete form"
#    ln -s /srv/jupyterhub/jupyterhub_form.complete.html /srv/jupyterhub/jupyterhub_form.html
#    ;;
#esac

# Configure according to selected authentication method
if [ -z "$AUTH_TYPE" ]; then
  echo "WARNING: Authentication type not specified. Defaulting to local LDAP."
  export AUTH_TYPE="local"
fi


case $AUTH_TYPE in
  "local")
    echo "CONFIG: User authentication via LDAP"
    ;;
  "shibboleth")
    echo "CONFIG: User authentication via Shibboleth"
    # Disable HTTPS rules on httpd (are included in config file for Shibboleth)
    mv /etc/httpd/conf.d/jupyterhub_ssl.conf /etc/httpd/conf.d/jupyterhub_ssl.noload
    # Enable Shibboleth rules on httpd
    mv /etc/httpd/conf.d/shib.noload /etc/httpd/conf.d/shib.conf
    sed "s/%%%HTTPS_PORT%%%/${HTTPS_PORT}/" /root/httpd_config/jupyterhub_shib.conf.template > /etc/httpd/conf.d/jupyterhub_shib.conf
    # Enable shibboleth daemon
    mv /etc/supervisord.d/shibd.noload /etc/supervisord.d/shibd.ini
    # Make sure the customization script puts in place all the remaining files
    if [ -z "$CUSTOMIZATION_REPO" ]; then
      echo "ERROR: Customization script is not set."
      echo "ERROR: The customization script should provide additional configuration files for Shibboleth authentication"
      echo "Cannot continue."
      exit 1
    echo "CONFIG: Plese make sure the customization script fetches all the required files (shibboleth2.yaml, attribute-map.xml, ...) for Shibboleth authentication."
    fi
    ;;
esac
# JRC - extract ldap certificate 
update-ca-trust extract


# Apply the customization script (if required)
if [ "$CUSTOMIZATION_REPO" ]; then
  CUSTOMIZATION_PATH="/tmp/customization"
  mkdir -p $CUSTOMIZATION_PATH
  echo "Fetching customizations from $CUSTOMIZATION_REPO"
  git config --global http.sslVerify false
  git clone $CUSTOMIZATION_REPO $CUSTOMIZATION_PATH
  cd $CUSTOMIZATION_PATH
  # Checkout specific commit, if set
  if [ "$CUSTOMIZATION_COMMIT" ]; then
    echo "Checkout commit $CUSTOMIZATION_COMMIT"
    git checkout $CUSTOMIZATION_COMMIT
  fi
  # Run the customization script
  if [ -z "$CUSTOMIZATION_SCRIPT" ]; then
    export CUSTOMIZATION_SCRIPT="entrypoint.sh"
  fi
  echo "Applying customizations via $CUSTOMIZATION_SCRIPT"
  sh $CUSTOMIZATION_SCRIPT
  cd /
fi



echo "Starting services..." 
/usr/bin/supervisord -c /etc/supervisord.conf
