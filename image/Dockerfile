FROM gitlab-registry.cern.ch/linuxsupport/alma9-base:20260929-1

LABEL maintainer="swan-admins@cern.ch"

ARG PYTHON_VERSION=3.14

# ----- Install CERN customizations ----- #

# Install support packages
# EPEL package needs to install first, so that we can install tini
RUN dnf install -y epel-release && \
    dnf install -y python3-pip \
                   # needed by kS4U
                   perl-Data-Dumper \
                   # needed by swanculler
                   sudo \
                   # useful for debugging
                   vim \
                   nano \
                   which \
                   tini && \
    dnf clean all && rm -rf /var/cache/dnf

ENV PATH="/opt/venv/bin:$PATH"

# Configure Python version and environment
RUN pip3 install --no-cache uv && \
    uv python install ${PYTHON_VERSION} && \
    uv venv /opt/venv --python ${PYTHON_VERSION} && \
    uv pip install \
        psycopg2-binary==2.9.13 \
        pycurl==7.48.0 \
        py-spy==0.4.2 \
        # SWAN packages
        keycloakauthenticator==4.0.13 \
        swanculler==1.0.9 \
        swanhub==1.0.24 \
        swanspawner==1.2.55


# Install kS4U
ADD ./bin/kS4U.pl /usr/bin/kS4U
ADD ./conf/krb5.conf /etc/krb5.conf
RUN chmod +x /usr/bin/kS4U && \
    dnf install -y perl-Authen-Krb5 && \
    dnf clean all && rm -rf /var/cache/dnf

# Install kubectl and helm (for sparkk8s_token.sh)
RUN curl -LO "https://dl.k8s.io/release/v1.34.4/bin/linux/amd64/kubectl" && \
    install -o root -g root -m 0755 kubectl /usr/bin/kubectl && rm kubectl && \
    curl -fsSL https://get.helm.sh/helm-v4.1.3-linux-amd64.tar.gz | tar xz && \
    install -o root -g root -m 0755 linux-amd64/helm /usr/bin/helm && rm -rf linux-amd64

# Add scripts for culler (EOS tickets) and token generation
COPY ./scripts/ /srv/jupyterhub/
RUN chmod -R 544 /srv/jupyterhub && \
    # Make jupyterhub execute swanhub instead. The JupyterHub chart uses
    # jupyterhub as the default command and so overwrites the CMD instruction
    # defined in this file.
    # https://github.com/jupyterhub/zero-to-jupyterhub-k8s/blob/4c186f90ce2fecdb66f4e11fbeba5aefc9016301/jupyterhub/templates/hub/deployment.yaml#L113
    ln -sf /opt/venv/bin/swanhub /opt/venv/bin/jupyterhub

# ----- Align with upstream image ----- #

EXPOSE 8081
ENTRYPOINT ["tini", "--"]
CMD ["/opt/venv/bin/jupyterhub", "--config", "/usr/local/etc/jupyterhub/jupyterhub_config.py"]
