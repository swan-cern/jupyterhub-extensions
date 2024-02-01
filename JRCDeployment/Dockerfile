#+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+#
#       |S|c|i|e|n|c|e| |B|o|x| |J|R|C|       #
#+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+#

# Docker file for JupyterHub image JRC

#FROM gitlab-registry.cern.ch/swan/docker-images/jupyterhub:v1.10
## 9/11/2021
FROM gitlab-registry.cern.ch/swan/docker-images/jupyterhub:v1.22


COPY rootfs /

# Copy the list of users with administrator privileges
ADD ./adminslist /srv/jupyterhub/adminslist

# Copy SSL certificates
ADD ./secrets/swan.cidsn.jrc.it.crt /etc/boxed/certs/boxed.crt
ADD ./secrets/swan.cidsn.jrc.it.csr /etc/boxed/certs/boxed.csr
ADD ./secrets/swan.cidsn.jrc.it.key /etc/boxed/certs/boxed.key

ADD ./secrets/cid_cacert.pem /etc/pki/ca-trust/source/anchors/cid_cacert.crt
ADD ./secrets/cid_cacert.pem /etc/pki/certs/cid_cacert.pem

RUN /usr/bin/python3 -m pip install --upgrade pip setuptools

# SAML -  OPT plugin for Jupyterhub
RUN pip install jupyterhub-samlauthenticator


# ----- sssd configuration ----- #
ADD ./sssd.d/sssd.conf /etc/sssd/sssd.conf
RUN chown root:root /etc/sssd/sssd.conf && \
    chmod 0600 /etc/sssd/sssd.conf

#Patch of jupytherhub to work with our double reverse proxies setup
#RUN yum --disablerepo=hdp7-stable --disablerepo=openstackclients7-queens-stable update && \
RUN yum --disablerepo=hdp7-stable --disablerepo=openstackclients7-queens-stable install -y patch && \
    yum clean all && \
    rm -rf /var/cache/yum

RUN patch -d /usr/local/lib/python3.6/site-packages/ -p1 < /root/jupyterhub-xorigin-fix.patch


#Without upgrade of setup tools, installation of JeodppSpawner class
#fails because of error
#error: setuptools 39.2.0 is installed but setuptools>=40.3.0 is required by {'google-auth'}
#
#pip has some recente changes to take into account, probably. This messages appears while building the cern image
#ERROR: After October 2020 you may experience errors when installing or updating packages. This is because pip will change the way that it resolves dependency conflicts.
#
#We recommend you use --use-feature=2020-resolver to test your packages with the new resolver before it becomes the default.
#
#google-auth 1.21.0 requires setuptools>=40.3.0, but you'll have setuptools 39.2.0 which is incompatible.
#RUN pip install --upgrade pip setuptools && \
#    pip install conu

RUN find / -xdev -name *.pyc -delete


### Security Issue from Paul
## 'rm /usr/hdp/hadoop-fetchdt-0.2.0/jars/hadoop-fetchdt-0.1.0-jar-with-dependencies.jar`
#[root@swan-dev-65f5548656-gmsxw /]# yum list installed | grep hadoop
#hadoop-fetchdt.noarch               0.2.0-1.el7.cern          @hdp7-stable
#[root@swan-dev-65f5548656-gmsxw /]#
RUN yum remove -y hadoop-fetchdt.noarch

#ADD ./JeodppSpawner/ /srv/jupyterhub/JeodppSpawner/
RUN cd /srv/jupyterhub/JeodppSpawner/ \
    && python3 setup.py install

ADD ./Media/Logo512.png /usr/local/share/jupyterhub/static/swan/logos/Logo512.png
ADD ./Media/JEODPP_swan-dev.ico /usr/local/share/jupyterhub/static/swan/logos/favicon.ico
ADD ./Media/logo_swan_jeodpp_dev.png /usr/local/share/jupyterhub/static/swan/logos/logo_swan_letters.png


#ADD ./jupyterhub.d/jupyterhub_config /root/jupyterhub_config

#ADD ./jupyterhub.d/jupyterhub_form.jeodpp-jhub.html   /srv/jupyterhub/jupyterhub_form.html
#ADD ./jupyterhub.d/form_options.json   /srv/jupyterhub/form_options.json

#ARG KUBE_VERSION="1.13.1"
#ARG KUBE_VERSION="1.15.1"

#RUN apk add --update ca-certificates && \
#    apk add --update -t deps curl jq bind-tools openssl && \
#    curl -L https://storage.googleapis.com/kubernetes-release/release/v$KUBE_VERSION/bin/linux/amd64/kubectl -o /usr/local/bin/kubectl && \
#    chmod +x /usr/local/bin/kubectl && \
#    apk del --purge deps && \
#    rm /var/cache/apk/*

#curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"

## Get latest tag
#VIEW_UTILIZATION_PATH=/usr/local/bin
#VIEW_UTILIZATION_TAG=$(curl -s https://api.github.com/repos/etopeter/kubectl-view-utilization/releases/latest | grep  "tag_name"| sed -E 's/.*"([^"]+)".*/\1/')
#
## Download and unpack plugin
#curl -sL "https://github.com/etopeter/kubectl-view-utilization/releases/download/${VIEW_UTILIZATION_TAG}/kubectl-view-utilization-${VIEW_UTILIZATION_TAG}.tar.gz" |tar xzvf - -C $VIEW_UTILIZATION_PATH
#
## Rename file if you want to use kubectl view-utilization or leave it if you want to invoke it with kubectl view utilization (with space between). Underscore between words allows kubernetes plugin to have hyphen between words.
#mv $VIEW_UTILIZATION_PATH/kubectl-view-utilization $VIEW_UTILIZATION_PATH/kubectl-view_utilization
#
## Change permission to allow execution
#chmod +x $VIEW_UTILIZATION_PATH/kubectl-view_utilization
#
## Check if plugin is detected
#kubectl plugin list

#RUN cd "$(mktemp -d)" && \
#    OS="$(uname | tr '[:upper:]' '[:lower:]')" && \
#    ARCH="$(uname -m | sed -e 's/x86_64/amd64/' -e 's/\(arm\)\(64\)\?.*/\1\2/' -e 's/aarch64$/arm64/')" && \
#    KREW="krew-${OS}_${ARCH}" && \
#    curl -fsSLO "https://github.com/kubernetes-sigs/krew/releases/latest/download/${KREW}.tar.gz" && \
#    tar zxvf "${KREW}.tar.gz" && \
#    ./"${KREW}" install krew
#
#
#
# RUN kubectl krew update; \
#     kubectl krew install view-utilization; \
#     kubectl krew upgrade view-utilization



#ADD start_proxy.sh /srv/jupyterhub/
#ADD ./jupyterhub.d/start.sh /root/start.sh

CMD ["/bin/bash", "/root/start.sh"]
