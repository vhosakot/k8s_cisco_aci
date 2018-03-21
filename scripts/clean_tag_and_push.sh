#!/bin/bash

#
# Be careful - this script deletes all the Docker containers and images
#
# steps to cleanup all the containers and images, build latest images of the
# CCP ACI service and the python client, tag them, and push them to the
# registry containers.cisco.com/contiv/ccp-aci-service

rm -rf clean_tag_and_push
mkdir clean_tag_and_push
cd clean_tag_and_push
git clone git@github.com:contiv/ccp_aci_service.git
cd ccp_aci_service

# delete all the Docker containers and images
sudo docker stop $(sudo docker ps -a -q)
sudo docker rm -f $(sudo docker ps -a -q)
sudo docker rmi -f $(sudo docker images -q)

./build_image.sh

sudo docker tag ccp-aci-service containers.cisco.com/contiv/ccp-aci-service:1.0
sudo docker push containers.cisco.com/contiv/ccp-aci-service:1.0

sudo docker tag ccp-aci-service containers.cisco.com/contiv/ccp-aci-service
sudo docker push containers.cisco.com/contiv/ccp-aci-service

cd python_client
sudo docker build --rm -t ccp-aci-client -f Dockerfile.python_client .
sudo docker tag ccp-aci-client containers.cisco.com/contiv/ccp-aci-service:python-client
sudo docker push containers.cisco.com/contiv/ccp-aci-service:python-client
cd ..

# delete all the Docker containers and images
sudo docker stop $(sudo docker ps -a -q)
sudo docker rm -f $(sudo docker ps -a -q)
sudo docker rmi -f $(sudo docker images -q)

cd ../..
rm -rf clean_tag_and_push

echo -e "\n Done!\n"
