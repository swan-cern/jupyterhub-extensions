#!/bin/bash
# Located at [/srv/jupyterhub/private/sparkk8s-token.sh]

function usage(){
  echo -e "usage: ${0} USERNAME \n"
  echo -e "USERNAME                      The username"
}

if [ "${1}" == "-h" ]; then
  usage
  exit
fi

if [[ -z "${1// }" ]]; then
  echo "ERROR: No username set"
  usage
  exit 1
fi
USERNAME="$1"
SERVICE_ACCOUNT="spark"

KUBECONFIG="/srv/jupyterhub/private/sparkk8s.cred"

if [[ ! -f $KUBECONFIG ]]; then
    exit 1
fi

SERVER=$(awk -F"server: " '{print $2}' ${KUBECONFIG} | sed '/^$/d')

# Check if the helm chart for the user is already installed
user_exists=$(helm --kubeconfig "${KUBECONFIG}" list -n ${USERNAME} --filter "spark-user-${USERNAME}" 2>/dev/null | grep -v NAMESPACE)

# Install the helm chart for the user if it does not exist
if [[ -z "${user_exists}" ]]; then
    # User not initialized
    helm install \
    spark-user-${USERNAME} \
    oci://registry.cern.ch/swan/charts/sparkk8s/cern-spark-user --version 1.0.5 \
    --kubeconfig "${KUBECONFIG}" \
    --namespace ${USERNAME} \
    --create-namespace \
    --set namespace=${USERNAME} \
    --set cvmfs.enable=true \
    --wait > /dev/null 2>&1
fi

# On development setups bypass all the rest of the logic for creating a limited-privs config
# and just use the admin config
# Note that this is not secure and should not be used in production
# Moreover, when testing the security of the spark service on dev, this should be manually disabled
if [ "$SWAN_DEV" = "true" ]; then
    echo $(cat $KUBECONFIG | base64 -w 0)
    exit 0
fi

# The secret name needs to be set to spark-token, this comes from the helm chart for spark-cern-user
SECRET="spark-token"

# Get the token for the service account
TOKEN=$(kubectl --kubeconfig="${KUBECONFIG}" \
--namespace "${USERNAME}" \
get secret "${SECRET}" -o json \
| python3 -c 'import json,sys;obj=json.load(sys.stdin);print(obj["data"]["token"])' | base64 --decode)

# get the ca.crt for the service account
CA=$(kubectl --kubeconfig="${KUBECONFIG}" \
--namespace "${USERNAME}" \
get secret "${SECRET}" -o json \
| python3 -c 'import json,sys;obj=json.load(sys.stdin);print(obj["data"]["ca.crt"])')

# Create a kubeconfig file for the user with limited privs
cat > /tmp/k8s-user.config.$USERNAME <<EOF
apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: $CA
    server: $SERVER
  name: k8s-spark-service
contexts:
- context:
    cluster: k8s-spark-service
    namespace: $USERNAME
    user: spark
  name: default
current-context: default
kind: Config
preferences: {}
users:
- name: spark
  user:
    token: $TOKEN
EOF

echo $(cat /tmp/k8s-user.config.$USERNAME | base64 -w 0)
