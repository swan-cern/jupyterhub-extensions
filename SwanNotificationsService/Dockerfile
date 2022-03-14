FROM gitlab-registry.cern.ch/linuxsupport/cs9-base:20220301-1.x86_64

RUN dnf install -y python3-pip && dnf clean all

#no version here as we will likely want to build the latest
RUN pip install --no-cache-dir swannotificationsservice

ENTRYPOINT ["/usr/local/bin/swannotificationsservice" ]
