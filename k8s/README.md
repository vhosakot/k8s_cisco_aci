## Steps to deploy CCP ACI service on kubernetes in CCP control plane

The etcd database is deployed as a sidecar container (`ccp-aci-server-etcd`) with the `ccp-aci-server` container in the same pod.

The helm chart and instructions to deploy the YAML files below on kubernetes using helm is in the `helm` directory.

The steps below were tested on k8s `1.9.0`.

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
4 S root         1     0  0  80   0 - 152041 wait  04:27 ?        00:00:01 /usr/bin/python /ccp_aci_server.py --ip 0.0.0.0 --port 46802 0.0.0.0:2379
4 S root        17     1  0  80   0 - 355052 poll_s 04:27 ?       00:00:06 /usr/bin/python /ccp_aci_server.py --ip 0.0.0.0 --port 46802 0.0.0.0:2379

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
    "git_sha1": "3a1b08e8d51c8e1224ba014e06bc2d0f0185b827", 
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

#### Delete the k8s deployment and service

```
$ kubectl delete -f deployment.yaml 
deployment "ccp-aci-server" deleted

$ kubectl delete -f service.yaml 
service "ccp-aci-server" deleted

$ kubectl get pods,svc
```
