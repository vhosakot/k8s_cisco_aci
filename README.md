## CCP ACI REST service

This repo has a RESTful server needed to create and delete configurations
asynchronously on the ACI fabric using the `acc-provision` tool and REST
APIs for each CCP tenant cluster.

## Architecture

```
                                           _________________
                                           |               |
    CCP tenant     <-->     CCP       <--> |   CCP ACI     |  <--> acc-provision <--> ACI fabric
Kubernetes cluster      control plane      |  REST service |
                                           |   ^        ^  |
                                           |   |        |  |
                                           |   |        |  |
                              |------------|   |        |  |-----------------|
                              |                v        v                    |
                              |  Allocator class <--> etcd database storing  |
                              |                       per-cluster state      |
                              |                       (sidecar container)    |
                              |                                              |
                              |----------------------------------------------|
                                         CCP ACI service pod in k8s
```

After configuring the ACI fabric, the CCP ACI REST service returns the ACI CNI
as a json needed for kubernetes in the HTTP response.

## Steps to build and run the Docker container with CCP ACI REST service

#### Build Docker image

```
git clone git@github.com:contiv/ccp_aci_service.git
cd ccp_aci_service
./build_image.sh

$ sudo docker images | grep ccp-aci-service
ccp-aci-service       latest              046c19d8d0ff        About a minute ago   1.2GB
```

The docker image is available in Docker Hub at https://hub.docker.com/r/contiv/ccp_aci_service/. Instead of building the docker image, to pull the image from Docker Hub, run:

```
docker pull contiv/ccp_aci_service
```

#### The CCP ACI REST service needs etcd database running and reachable

Start etcd database in a Docker container:

```
sudo docker run -d -p 2379:2379 --name etcd-3 --net=host \
    k8s.gcr.io/etcd-amd64:3.1.11 \
    etcd --listen-client-urls http://0.0.0.0:2379 \
    --advertise-client-urls http://0.0.0.0:2379

$ sudo docker ps -a | grep etcd
16a05e186ff3        k8s.gcr.io/etcd-amd64:3.1.11   "etcd --listen-clien…"   6 minutes ago    Up 6 minutes    etc-3
```

#### Run CCP ACI REST service in Docker container

```
sudo docker run --name ccp-aci-service --net=host -d -p 46802:46802 ccp-aci-service

$ sudo docker ps -a | grep ccp-aci-service
b6ba236f2c82     ccp-aci-service    "/ccp_aci_ser…"   2 minutes ago   Up 2 minutes   ccp-aci-service
```

If the docker image is not built but pulled from Docker Hub, to run the image pulled from Docker Hub, run:

```
sudo docker run --name ccp-aci-service --net=host -d -p 46802:46802 contiv/ccp_aci_service
```

#### (Optional) To use non-default IP address and non-default port

The default port used by the CCP ACI service `46802`. The default port used by etcd is `2379`.

To use the following non-default values:

CCP ACI service listening at `10.10.10.10` and port `46808`, and
etcd listening at `20.20.20.20` and port `3379`, run:

```
sudo docker run --name ccp-aci-service --net=host -d -p 46808:46808 ccp-aci-service \
    sh -c "/ccp_aci_server.py --ip 10.10.10.10 --port 46808 20.20.20.20:3379"

$ sudo docker ps -a | grep ccp-aci-service
18f4ab9c9bf6    ccp-aci-service    "sh -c '/ccp_…"   8 seconds ago    Up 6 seconds     ccp-aci-service
```

#### Check the output of REST server in the container logs

**NOTE**: Make sure that the host running the `ccp-aci-service` container can ping the ACI APIC fabric.

```
$ sudo docker logs ccp-aci-service
 * Running on http://0.0.0.0:46802/ (Press CTRL+C to quit)
 * Restarting with stat
 * Debugger is active!
 * Debugger PIN: 161-563-901
```

#### (Optional) Exec into the container and check the CCP ACI REST service

```
$ sudo docker exec -it ccp-aci-service /bin/bash
root@vhosakot-contiv-vpp:/ccp-aci-certs# ps -ef
UID        PID  PPID  C STIME TTY          TIME CMD
root         1     0  0 14:49 ?        00:00:00 /usr/bin/python /ccp_aci_server.
root        17     1  1 14:49 ?        00:00:01 /usr/bin/python /ccp_aci_server.
root       147     0  0 14:50 pts/0    00:00:00 /bin/bash
root       157   147  0 14:50 pts/0    00:00:00 ps -ef
root@vhosakot-contiv-vpp:/ccp-aci-certs# pwd
/ccp-aci-certs
root@vhosakot-contiv-vpp:/ccp-aci-certs# ls -l / | grep 'ccp_aci_service_version\|py$'
-rw-rw-r--   1 root root  8912 Mar  5 03:25 allocator.py
-rwxrwxrwx   1 root root  9628 Mar  5 13:49 ccp_aci_server.py
-rw-rw-r--   1 root root    41 Mar  5 03:25 ccp_aci_service_version
-rwxrwxr-x   1 root root 24259 Mar  5 03:25 server.py
root@vhosakot-contiv-vpp:/ccp-aci-certs# exit
```

#### curl the CCP ACI REST service to see the REST API operations supported

`172.18.7.254` below is the IP address of the host that runs the `ccp-aci-service` container.

```
$ curl 172.18.7.254:46802
{
  "acc-provision": {
    "git_sha1": "eb1b634959fd6925c7c75e1ecb250209fdbc8f73", 
    "url": [
      "HTTP POST   /api/v1/acc_provision_create", 
      "HTTP DELETE /api/v1/acc_provision_delete", 
      "HTTP GET    /api/v1/acc_provision_status", 
      "HTTP GET    /"
    ], 
    "version": "1.8.0"
  }
}
```

The above url `172.18.7.254:46802` can be used for `httpGet` of kubernetes' `livenessProbe` to probe the health of this service in k8s. This url makes sure that:

* etcd database is up
* `acc-provision` tool works
* The CCP ACI service is up

`git_sha1` above is the git SHA1 of the latest commit in this repo and `version` above is the version of `acc-provision` tool.

#### Run the CCP ACI client `python_client/ccp_aci_client` to create configurations on the ACI fabric asynchronously using HTTP POST

This is `HTTP POST` to endpoint `/api/v1/acc_provision_create`.

`172.18.7.254` below is the IP address of the host that runs the `ccp-aci-service` container.
`admin` is the ACI APIC username, `cisco123!` is the ACI APIC password.
`10.23.231.5` below is the IP address of ACI APIC.
`create / status / delete` is the HTTP operation.
`1.7` is the kubernetes version.

```
$ cd python_client
$ ./ccp_aci_client 172.18.7.254 my_cluster1 admin cisco123! create \
      --aci_apic_hosts 10.23.231.5 --k8s_version 1.7

status code =  202
HTTP response =  {
    "response": "Request accepted to create ACI configs. Use http endpoint /api/v1/acc_provision_status to get the ACI CNI for the cluster."
}
```

#### Run the CCP ACI client `python_client/ccp_aci_client` to get the ACI CNI as a json needed for kubernetes using HTTP GET

This is `HTTP GET` from endpoint `/api/v1/acc_provision_status`.

```
$ cd python_client
$ ./ccp_aci_client 172.18.7.254 my_cluster1 admin cisco123! status

Done! ACI CNI YAML file is aci_cni_my_cluster1.yaml in the current directory

$ ls -l aci_cni_my_cluster1.yaml
-rw-rw-r-- 1 ubuntu ubuntu 13767 Mar  2 19:15 aci_cni_my_cluster1.yaml
```

The above step creates the ACI CNI YAML file `aci_cni_my_cluster1.yaml` in the current directory. This can be used to install ACI CNI in kubernetes using the command:

```
sudo kubectl apply -f aci_cni_my_cluster1.yaml
```

#### Use the ACI CNI YAML file `aci_cni_my_cluster1.yaml` in the current directory to install ACI CNI on kubernetes

Make sure that there is no other CNI running in kubernetes. If so, do `sudo kubeadm reset` on all the nodes, reboot all the nodes, do `sudo kubeadm init` on the master node, do `kubeadm join --token ...` on all the worker nodes, wait for 5 minutes, and then install the ACI CNI YAML `aci_cni_my_cluster1.yaml` on kubernetes.

```
$ sudo kubectl apply -f aci_cni_my_cluster1.yaml
configmap "aci-containers-config" created
secret "aci-user-cert" created
serviceaccount "aci-containers-controller" created
serviceaccount "aci-containers-host-agent" created
clusterrole "aci-containers:controller" created
clusterrole "aci-containers:host-agent" created
clusterrolebinding "aci-containers:controller" created
clusterrolebinding "aci-containers:host-agent" created
daemonset "aci-containers-host" created
daemonset "aci-containers-openvswitch" created
deployment "aci-containers-controller" created

$ kubectl get pods -n=kube-system | grep -i aci-c
aci-containers-controller-2834261735-7q3ql           1/1       Running            0          3m
aci-containers-host-1pfdt                            3/3       Running            0          3m
aci-containers-host-jx4m6                            3/3       Running            0          3m
aci-containers-host-p5xbt                            3/3       Running            0          3m
aci-containers-openvswitch-h1q2f                     1/1       Running            0          3m
aci-containers-openvswitch-ppmsd                     1/1       Running            0          3m
aci-containers-openvswitch-ttnrj                     1/1       Running            0          3m
```

Make sure that the `my_cluster1` tenant is created in the "Tenants" tab in the ACI APIC fabric at https://10.23.231.5.

#### (Optional) Check the state stored by the CCP ACI service in etcd database

```
sudo docker exec -it -e ETCDCTL_API=3 etcd-3 etcdctl get --prefix /
```

#### Run the CCP ACI client `python_client/ccp_aci_client` to delete configurations on the ACI fabric asynchronously using HTTP DELETE

This is `HTTP DELETE` to endpoint `/api/v1/acc_provision_delete`.

```
$ cd python_client
$ ./ccp_aci_client 172.18.7.254 my_cluster1 admin cisco123! delete

status code =  202
HTTP response =  {
    "response": "Request accepted to delete ACI configs. Use http endpoint /api/v1/acc_provision_status to get the status."
}
```

#### Run the CCP ACI client `python_client/ccp_aci_client` to make sure that ACI configurations are successfully deleted using HTTP GET

This is `HTTP GET` from endpoint `/api/v1/acc_provision_status`.

```
$ cd python_client
$ ./ccp_aci_client 172.18.7.254 my_cluster1 admin cisco123! status

status code =  404
HTTP response =  {
    "error": "ERROR: ACI CNI not found for cluster. Use http endpoint /api/v1/acc_provision_create to create (POST) configs on ACI first, and then use this endpoint to get the ACI CNI for the cluster. If http endpoint /api/v1/acc_provision_delete was used to delete the ACI configs, then this message means the deletion was successful."
}
```

The above HTTP return code `404` means that the ACI configurations were successfully deleted on the ACI fabric.

Make sure that the `my_cluster1` tenant is deleted in the "Tenants" tab in the ACI APIC fabric at https://10.23.231.5.

#### Stop the containers, remove them and remove the images

```
sudo docker stop ccp-aci-service
sudo docker rm ccp-aci-service
sudo docker stop etcd-3
sudo docker rm etcd-3
sudo docker rmi -f ccp-aci-service
sudo docker rmi -f k8s.gcr.io/etcd-amd64:3.1.11
```

#### Download the `acc-provision` tool from https://software.cisco.com/download/type.html?mdfid=285968390&i=rm:

APIC OpenStack and Container Plugins --> 3.1 --> Debian packages for ACI Kubernetes 1.7 tools

#### Useful directories

* The kubernetes manifest YAML files to install the k8s deployment and service for the CCP ACI server are in the directory `k8s`.

* The helm chart and instructions to install CCP ACI service using helm is in the `k8s/helm` directory.

* The API spec for HTTP clients are in the directory `api_spec/api_spec.md`.

* `sudo make install` will install the `acc-provision` tool along with the required `pip` and `apt-get` dependecies needed for this repo on an Ubuntu host.

* The ACI configurations for `server/allocator.py` can be specified in `server/aci.conf` and in the configMap `k8s/configmap.yaml` on kubernetes.

#### Testing

Stop and remove `etcd` container if running:

```
sudo docker ps -a | grep -i etcd
```

Run the following steps to run the tests for `server/allocator.py`:

```
sudo pip install -r requirements.txt
sudo make tests
```
