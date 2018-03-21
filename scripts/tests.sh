#!/bin/bash

set -euo pipefail

IMAGE_NAME="ccp_aci_service_tests"
NETWORK_NAME="$IMAGE_NAME"
ETCD_CONTAINER_NAME="etcd_ccp_api_service_unittests"

echo "Building tests image..."
docker build -t $IMAGE_NAME -f ./Dockerfile.tests .

function ip_for_container() {
	docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $1
}

# ----- SETUP -------------------------------------------------------------------

# clean up olds runs
docker rm -fv $ETCD_CONTAINER_NAME 2>/dev/null || :
docker network rm $NETWORK_NAME 2>/dev/null || :

echo "Creating docker network $NETWORK_NAME"
docker network create $NETWORK_NAME

echo "Starting etcd container..."
ETCD_CONTAINER_ID=$(
	docker run -d \
		-p 2379:2379 \
		--name $ETCD_CONTAINER_NAME \
		--network $NETWORK_NAME \
                k8s.gcr.io/etcd-amd64:3.1.11 \
		etcd \
		--listen-client-urls http://0.0.0.0:2379 \
		--advertise-client-urls http://0.0.0.0:2379
)
ETCD_CONTAINER_IP=$(ip_for_container $ETCD_CONTAINER_ID)
echo "etcd running @ $ETCD_CONTAINER_IP:2379"

# ----- EXECUTION ---------------------------------------------------------------

echo "Running unit tests"

set +e

docker run --rm \
	--network $NETWORK_NAME \
	--name $IMAGE_NAME \
	-e ETCD_CONTAINER_IP="$ETCD_CONTAINER_IP" \
	$IMAGE_NAME
test_exit_code=$?

set -e

# ----- CLEANUP -----------------------------------------------------------------

echo "Shutting down etcd container..."
docker rm -fv $ETCD_CONTAINER_NAME

echo "Destroying docker network $NETWORK_NAME"
docker network rm $NETWORK_NAME

if [[ "$test_exit_code" != "0" ]]; then
	echo "Tests failed with exit code: $test_exit_code"
	exit 1
fi
