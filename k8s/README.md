## Steps to deploy CCP ACI service on kubernetes in CCP control plane

The etcd database is deployed as a sidecar container (`ccp-aci-server-etcd`) with the `ccp-aci-server` container in the same pod.

The helm chart and instructions to deploy the YAML files below on kubernetes using helm is in the `helm` directory.

The steps below were tested on k8s `1.9.0`.

#### Create the configmap

```
$ kubectl create -f configmap.yaml 
configmap "ccp-aci-server-configmap" created
```

#### Create the deployment

```
$ kubectl create -f deployment.yaml 
deployment "ccp-aci-server" created
```

#### Create the service

```
$ kubectl create -f service.yaml 
service "ccp-aci-server" created
```

#### Check the pod and the `ccp-aci-server` and `ccp-aci-server-etcd` containers

```
$ kubectl get pods
NAME                             READY     STATUS    RESTARTS   AGE
ccp-aci-server-7c44dff49-cbflq   2/2       Running   1          6m

$ kubectl describe pod ccp-aci-server-7c44dff49-cbflq | grep 'ccp-aci-server:\|ccp-aci-server-etcd:\|Image:'
  ccp-aci-server:
    Image:         containers.cisco.com/contiv/ccp-aci-service:1.0
  ccp-aci-server-etcd:
    Image:         k8s.gcr.io/etcd-amd64:3.1.11
```

#### Check the configmap for aci.conf

```
$ kubectl get configmaps | grep aci
ccp-aci-server-configmap          1         1m

$ kubectl describe configmap ccp-aci-server-configmap
Name:         ccp-aci-server-configmap
Namespace:    default
Labels:       app=aci-server
Annotations:  <none>

Data
====
aci.conf:
----
[DEFAULT]
DEFAULT_VLAN_MIN = 3130

# DEFAULT_VLAN_MAX's maximum value is 4095
DEFAULT_VLAN_MAX = 3800

# DEFAULT_MULTICAST_RANGE should be a multicast range
DEFAULT_MULTICAST_RANGE = 225.65.0.0/16

DEFAULT_SERVICE_SUBNET = 100.33.0.0/24

# DEFAULT_POD_SUBNET has to end with .1
DEFAULT_POD_SUBNET = 100.44.55.1/16

Events:  <none>
```

#### Check the `ccp-aci-server` service

```
$ kubectl get svc | grep aci
ccp-aci-server   ClusterIP   10.100.49.102   <none>        46802/TCP   7m

$ kubectl describe svc ccp-aci-server
Name:              ccp-aci-server
Namespace:         default
Labels:            app=aci-server
Annotations:       <none>
Selector:          app=aci-server
Type:              ClusterIP
IP:                10.100.49.102
Port:              http  46802/TCP
TargetPort:        46802/TCP
Endpoints:         172.17.0.5:46802
Session Affinity:  None
Events:            <none>
```

The `ccp-aci-server` k8s service above is of type `ClusterIP` and listening on port `46802`.

#### Check pod's logs

```
$ kubectl logs ccp-aci-server-7c44dff49-cbflq -c=ccp-aci-server
 * Running on http://0.0.0.0:46802/ (Press CTRL+C to quit)
 * Restarting with stat
 * Debugger is active!
 * Debugger PIN: 189-664-447
172.17.0.1 - - [15/Mar/2018 04:29:11] "GET / HTTP/1.1" 200 -
172.17.0.1 - - [15/Mar/2018 04:30:12] "GET / HTTP/1.1" 200 -
172.17.0.1 - - [15/Mar/2018 04:31:11] "GET / HTTP/1.1" 200 -

$ kubectl logs ccp-aci-server-7c44dff49-cbflq -c=ccp-aci-server-etcd
```

#### Check the processes running in the two containers

```
$ kubectl exec ccp-aci-server-7c44dff49-cbflq -c=ccp-aci-server -- ps -elf
F S UID        PID  PPID  C PRI  NI ADDR SZ WCHAN  STIME TTY          TIME CMD
4 S root         1     0  0  80   0 - 152041 wait  04:27 ?        00:00:01 /usr/bin/python /ccp_aci_server.py --ip 0.0.0.0 --port 46802 --config_file /aci.conf 0.0.0.0:2379
4 S root        17     1  0  80   0 - 355052 poll_s 04:27 ?       00:00:06 /usr/bin/python /ccp_aci_server.py --ip 0.0.0.0 --port 46802 --config_file /aci.conf 0.0.0.0:2379

$ kubectl exec ccp-aci-server-7c44dff49-cbflq -c=ccp-aci-server-etcd -- ps -elf
PID   USER     TIME   COMMAND
    1 root       0:08 etcd --listen-client-urls http://0.0.0.0:2379 --advertise-client-urls http://0.0.0.0:2379
```

#### Curl and check if the `ccp-aci-server` k8s service is up in the CCP control plane

`10.100.49.102` below is the `ClusterIP` of the `ccp-aci-server` k8s service listening on port `46802`.

```
$ minikube ssh "curl 10.100.49.102:46802"
{
  "acc-provision": {
    "git_sha1": "f85f2e9e3ad72a606f84b5d21986bc79f1606d00", 
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

#### Check contents of the configmap for aci.conf inside the `ccp-aci-server` container

```
$ kubectl exec ccp-aci-server-7c44dff49-cbflq -c=ccp-aci-server cat /aci.conf
[DEFAULT]
DEFAULT_VLAN_MIN = 3130

# DEFAULT_VLAN_MAX's maximum value is 4095
DEFAULT_VLAN_MAX = 3800

# DEFAULT_MULTICAST_RANGE should be a multicast range
DEFAULT_MULTICAST_RANGE = 225.65.0.0/16

DEFAULT_SERVICE_SUBNET = 100.33.0.0/24

# DEFAULT_POD_SUBNET has to end with .1
DEFAULT_POD_SUBNET = 100.44.55.1/16
```

#### (Optional) Check the state in etcd database inside the `ccp-aci-server-etcd` container

```
kubectl exec ccp-aci-server-7c44dff49-cbflq -c=ccp-aci-server-etcd -- sh -c "ETCDCTL_API=3 etcdctl get --prefix /"
```

Now, the CCP ACI service can be used to configure ACI and get the ACI CNI needed for kubernetes.

#### See logs of the liveness probe sent by k8s to the `ccp-aci-server` container once every minute

Run the command below once every minute to see the liveness probe's logs:

```
$ kubectl logs ccp-aci-server-7c44dff49-cbflq -c=ccp-aci-server
 * Running on http://0.0.0.0:46802/ (Press CTRL+C to quit)
 * Restarting with stat
 * Debugger is active!
 * Debugger PIN: 189-664-447
172.17.0.1 - - [15/Mar/2018 04:29:11] "GET / HTTP/1.1" 200 -
172.17.0.1 - - [15/Mar/2018 04:30:12] "GET / HTTP/1.1" 200 -
172.17.0.1 - - [15/Mar/2018 04:31:11] "GET / HTTP/1.1" 200 -
172.17.0.1 - - [15/Mar/2018 04:32:11] "GET / HTTP/1.1" 200 -
172.17.0.1 - - [15/Mar/2018 04:33:11] "GET / HTTP/1.1" 200 -
172.17.0.1 - - [15/Mar/2018 04:34:11] "GET / HTTP/1.1" 200 -
172.17.0.1 - - [15/Mar/2018 04:35:11] "GET / HTTP/1.1" 200 -
172.17.0.1 - - [15/Mar/2018 04:36:11] "GET / HTTP/1.1" 200 -
172.17.0.1 - - [15/Mar/2018 04:37:11] "GET / HTTP/1.1" 200 -
172.17.0.1 - - [15/Mar/2018 04:38:12] "GET / HTTP/1.1" 200 -
```

#### How to use the python client to simulate CORC in CCP and test the CCP ACI service in kubernetes

The python client `python_client/ccp_aci_client` is available in a Docker container at `containers.cisco.com/contiv/ccp-aci-service:python-client` and can be used to simulate CORC in CCP and test the CCP ACI service in kubernetes using the following steps:

```
$ kubectl run ccp-aci-server-python-client --image=containers.cisco.com/contiv/ccp-aci-service:python-client
deployment "ccp-aci-server-python-client" created

$ kubectl get pods
NAME                                            READY     STATUS    RESTARTS   AGE
ccp-aci-server-7c44dff49-cbflq                  2/2       Running   1          18m
ccp-aci-server-python-client-6479775848-dklxf   1/1       Running   0          17s

$ kubectl exec -it ccp-aci-server-python-client-6479775848-dklxf curl 10.100.49.102:46802
{
  "acc-provision": {
    "git_sha1": "f85f2e9e3ad72a606f84b5d21986bc79f1606d00", 
    "url": [
      "HTTP POST   /api/v1/acc_provision_create", 
      "HTTP DELETE /api/v1/acc_provision_delete", 
      "HTTP GET    /api/v1/acc_provision_status", 
      "HTTP GET    /"
    ], 
    "version": "1.8.1"
  }
}

# Create configurations on the ACI fabric for the CCP tenant cluster my_cluster1
$ kubectl exec -it ccp-aci-server-python-client-6479775848-dklxf -- /ccp_aci_client 10.100.49.102 \
      my_cluster1 admin cisco123! create --aci_apic_hosts 10.23.231.5 --k8s_version 1.7

# Get the ACI CNI needed for k8s
$ kubectl exec -it ccp-aci-server-python-client-6479775848-dklxf -- /ccp_aci_client 10.100.49.102 \
      my_cluster1 admin cisco123! status

# Make sure that the my_cluster1 tenant is created in the "Tenants" tab in the ACI APIC fabric at https://10.23.231.5.

# Delete configurations on the ACI fabric for the CCP tenant cluster my_cluster1
$ kubectl exec -it ccp-aci-server-python-client-6479775848-dklxf -- /ccp_aci_client 10.100.49.102 \
      my_cluster1 admin cisco123! delete

# Make sure that the my_cluster1 tenant is deleted in the "Tenants" tab in the ACI APIC fabric at https://10.23.231.5.

# Delete the ccp-aci-server-python-client pod
$ kubectl delete deployment ccp-aci-server-python-client
deployment "ccp-aci-server-python-client" deleted
```

#### Delete the k8s deployment, service and configmap

```
$ kubectl delete -f deployment.yaml 
deployment "ccp-aci-server" deleted

$ kubectl delete -f service.yaml 
service "ccp-aci-server" deleted

$ kubectl get pods,svc,configmaps
```
