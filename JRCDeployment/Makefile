#Dockerfile vars
dockerfile="Dockerfile"
tag="sb0.1"
cluster="new"

#vars
IMAGENAME="swan-jupyterhub-dev"
REPO="jeoreg.cidsn.jrc.it:5000"
REPONS="jeodpp-k8s"
IMAGEFULLNAME=${REPO}/${REPONS}/${IMAGENAME}:${tag}
PKEY="/home/marlelu/.ssh/id_rsa"
HOSTFILE="/eos/jeodpp/home/users/marlelu/bash/hosts_k8s_"${cluster}

PSSHPULL="pssh -i -t 0 -l root -x 'pkey=${PKEY}' -h ${HOSTFILE} -- \"docker pull ${IMAGEFULLNAME}\""

.PHONY: help build push all

help:
	@echo "Makefile arguments:"
	@echo ""
	@echo "tag - Tag for the Docker image"
	@echo "cluster - suffix for K8S cluster for pulling the image build (old or new)"
	@echo "-------------------------------------------------------------------------"
	@echo "Makefile commands:"
	@echo "build"
	@echo "push - push image into the registry"
	@echo "pssh - show the pssh command to be execute manually or with   make pull"
	@echo "pull - execute the pssh command to pull the image into the K8s hosts"
	@echo "all"

.DEFAULT_GOAL := all

build:
	@docker build --pull -t ${IMAGEFULLNAME} .

buildkit:
	@DOCKER_BUILDKIT=1 docker build --pull -t ${IMAGEFULLNAME} -f ${dockerfile} . 2>&1 | tee temporary_build_log_${tag}.txt

pssh:
	@echo "Makefile arguments: "
	@echo ""
	@echo "tag - Tag for the Docker image"
	@echo "cluster - suffix for K8S cluster for pulling the image build (old or new)"
	@echo "-------------------------------------------------------------------------"
	@echo "Manually execute to pull image on K8S ${cluster} cluster:"
	@echo ""
	@echo ${PSSHPULL}

push:
	@docker login ${REPO}
	@docker push ${IMAGEFULLNAME}

pull:
	@eval ${PSSHPULL}

all: buildkit push pssh
