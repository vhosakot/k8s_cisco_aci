#!/bin/bash

# get latest git sha1
> ccp_aci_service_version
git log -1 --format=format:%H > ccp_aci_service_version

# build ccp-aci-service docker image
sudo docker build --rm -t ccp-aci-service .
