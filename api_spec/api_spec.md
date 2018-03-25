## REST API spec for HTTP clients

This document has the REST API specifications needed for HTTP clients interacting with the CCP ACI REST service to create and delete configs on the ACI fabric asynchronously for a CCP tenant cluster. There is a sample python HTTP client `python_client/ccp_aci_client` in this repo that can be used as reference.

#### The CCP ACI REST service supports the following three APIs:

1. `HTTP POST` `/api/v1/acc_provision_create` to create configurations on ACI asynchronously for a CCP tenant cluster

2. `HTTP GET` `/api/v1/acc_provision_status` to get the ACI CNI as json if it exists for the cluster

3. `HTTP DELETE` `/api/v1/acc_provision_delete` to delete configurations on ACI asynchronously for the cluster

The sample python HTTP client `python_client/ccp_aci_client` in this repo has sample http payloads for these three REST APIs.

## HTTP payload format that need to be sent by clients

#### Request format for `/api/v1/acc_provision_create`

Example below is for:

```
ccp_cluster_name : my_cluster_1
aci_username : admin
aci_password : cisco123!
apic_hosts : 10.23.231.5
k8s_version : 1.7
```

**NOTE:** All the keys below should be set by the http client and/or retrieved from:

* CCP GUI
* CCP database
* ACI profile in the GUI

Refer the python function `get_sample_input_json()` in the sample python HTTP client `python_client/ccp_aci_client` for sample python code to
create and update this sample input json below in the client.

```
{
    "aci_username": "admin", 
    "ccp_cluster_name": "my_cluster_1", 
    "aci_password": "cisco123!", 
    "k8s_version": "1.7", 
    "aci_input_json": {
        "net_config": {
            "extern_static": "1.4.0.1/24", 
            "infra_vlan": 4093, 
            "extern_dynamic": "1.3.0.1/24", 
            "node_subnet": "1.10.58.1/24"
        }, 
        "aci_config": {
            "l3out": {
                "external_networks": [
                    "hx-ext-net"
                ], 
                "name": "hx-l3out"
            }, 
            "aep": "hx-aep", 
            "apic_hosts": [
                "10.23.231.5"
            ], 
            "vrf": {
                "name": "hx-l3out-vrf", 
                "tenant": "common"
            }, 
            "vmm_domain": {
                "encap_type": "vxlan", 
                "nested_inside": {
                    "type": "vmware", 
                    "name": "hx8-vcenter"
                }
            }
        }, 
        "registry": {
            "image_prefix": "noiro"
        }
    }
}
```

#### Respose format for `/api/v1/acc_provision_create`

HTTP status code `202`:

```
{
    "response": "Request accepted to create ACI configs. Use http endpoint /api/v1/acc_provision_status to get the ACI CNI for the cluster."
}
```

HTTP status code `400` for duplicate cluster name `my_cluster_1` that already exists in the server's etcd database:

```
{
    "error": "Duplicate cluster name my_cluster_1. Use a different cluster name."
}
```

#### Request format for `/api/v1/acc_provision_status`

Example below is for:

```
ccp_cluster_name : my_cluster_1
aci_username : admin
aci_password : cisco123!
```

```
{
    "aci_username": "admin", 
    "ccp_cluster_name": "my_cluster_1", 
    "aci_password": "cisco123!"
}

```

#### Response format for `/api/v1/acc_provision_status`

The response has HTTP status code `200` with the following **three** keys:

* `ccp_cluster_name` - This key has the CCP tenant cluster name for which the ACI configurations were successfully created.

* `aci_cni_response` - ACI CNI json for the cluster needed for `kubectl apply` in kubernetes.

* `allocator_state`  - The state reserved by the `Allocator` class for the CCP tenant cluster.

Refer the python function `convert_json_to_aci_cni_yaml()` in the sample python HTTP client `python_client/ccp_aci_client` for sample python code to convert this ACI CNI json in the key `aci_cni_response` below to a YAML file that can be used with `kubectl apply -f <YAML filename>`.

```
{
    "ccp_cluster_name": "my_cluster_1", 
    "aci_cni_response": [
        {
            "kind": "ConfigMap", 
            "data": {
                "host-agent-config": "{\n    \"log-level\": \"info\",\n    \"aci-vmm-type\": \"Kubernetes\",\n    \"aci-vmm-domain\": \"my_cluster_1\",\n    \"aci-vmm-controller\": \"my_cluster_1\",\n    \"aci-vrf\": \"hx-l3out-vrf\",\n    \"aci-vrf-tenant\": \"common\",\n    \"service-vlan\": 2121,\n    \"encap-type\": \"vxlan\",\n    \"aci-infra-vlan\": 4093,\n    \"cni-netconfig\": [\n        {\n            \"routes\": [\n                {\n                    \"gw\": \"1.60.0.1\", \n                    \"dst\": \"0.0.0.0/0\"\n                }\n            ], \n            \"subnet\": \"1.60.0.0/16\", \n            \"gateway\": \"1.60.0.1\"\n        }\n    ]\n}", 
                "opflex-agent-config": "{\n    \"log\": {\n        \"level\": \"info\"\n    },\n    \"opflex\": {\n    }\n}", 
                "controller-config": "{\n    \"log-level\": \"info\",\n    \"apic-hosts\": [\n        \"10.23.231.5\"\n    ],\n    \"apic-username\": \"my_cluster_1\",\n    \"apic-private-key-path\": \"/usr/local/etc/aci-cert/user.key\",\n    \"aci-prefix\": \"my_cluster_1\",\n    \"aci-vmm-type\": \"Kubernetes\",\n    \"aci-vmm-domain\": \"my_cluster_1\",\n    \"aci-vmm-controller\": \"my_cluster_1\",\n    \"aci-policy-tenant\": \"my_cluster_1\",\n    \"require-netpol-annot\": false,\n    \"aci-service-phys-dom\": \"my_cluster_1-pdom\",\n    \"aci-service-encap\": \"vlan-2121\",\n    \"aci-service-monitor-interval\": 15,\n    \"aci-vrf-tenant\": \"common\",\n    \"aci-l3out\": \"hx-l3out\",\n    \"aci-ext-networks\": [\n        \"hx-ext-net\"\n    ],\n    \"aci-vrf\": \"hx-l3out-vrf\",\n    \"default-endpoint-group\": {\n        \"policy-space\": \"my_cluster_1\",\n        \"name\": \"kubernetes|kube-default\"\n    },\n    \"namespace-default-endpoint-group\": {\n        \"kube-system\": {\n            \"policy-space\": \"my_cluster_1\",\n            \"name\": \"kubernetes|kube-system\"\n        }\n    },\n    \"service-ip-pool\": [\n        {\n            \"start\": \"1.3.0.2\", \n            \"end\": \"1.3.0.254\"\n        }\n    ],\n    \"static-service-ip-pool\": [\n        {\n            \"start\": \"1.4.0.2\", \n            \"end\": \"1.4.0.254\"\n        }\n    ],\n    \"pod-ip-pool\": [\n        {\n            \"start\": \"1.60.0.2\", \n            \"end\": \"1.60.255.254\"\n        }\n    ],\n    \"node-service-ip-pool\": [\n        {\n            \"start\": \"10.5.0.2\", \n            \"end\": \"10.5.0.254\"\n        }\n    ],\n    \"node-service-subnets\": [\n        \"10.5.0.0/24\"\n    ]\n}"
            }, 
            "apiVersion": "v1", 
            "metadata": {
                "labels": {
                    "network-plugin": "aci-containers", 
                    "aci-containers-config-version": "5d1daa9d-a8f2-496e-a414-8c0413991bfa"
                }, 
                "namespace": "kube-system", 
                "name": "aci-containers-config"
            }
        }, 
        {
            "kind": "Secret", 
            "data": {
                "user.key": "LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tCk1JSUNkUUlCQURBTkJna3Foa2lHOXcwQkFRRUZBQVNDQWw4d2dnSmJBZ0VBQW9HQkFObDgva0FNcTR4c2F3aVEKUEJaNUNtK1ovaG42MFNnaVJKcGttUjE4cGFnVmVTWGNvRjlrTzFCaDgzcDlDQUFxWGpXYXpjMkhtWVQyWXl5SgpTVWFVdEY0Z0hoZDdUMVN0UkxSWDhEc1ZYcEJCZ2JodlYveUlXa0dCdWFZeGtoaXVBTWFoS3hOZlp5WkNUOXA0CnpRT1lXUjlnZkIxRGFPeXA3a1d3bzBWMHc0ZXJBZ01CQUFFQ2dZQWV4UWhUbDNkTnpxajE5VElMRytUV0ZUdFcKQVo1RngxTmRaSTRsRmRWNkNrK3hnNTFNNGFsaW5ma01nMVAyY2dnU0hXeXdmMWJBOFBybStpVmJ6djRWY0VGYgp2TEc2TysxWGV2eDFRY0c0V3lLK0wzcEZ4c3NVNzliSGpCT1NxNU9mUk1Rdk4wc3Mvd1U5Q1p2cUZUUjdHc2d6CmxVZkoxVGc0RWxVc1lpbFlnUUpCQU96ZnE3MTVQV25CT3lyZEo0VXlRRmxLeWtwN0M4RkNiSHY1dTNNcEl3SC8KYmFUYVEyTkNCZVNxTmVJMGY0Mk5UVk5rL0NXcVBTQUpwU1hpZmlXTlV3TUNRUURyREp6VXFDMXFudjFBMkZETAoxc1h4b0hsMVFERUdQYmh5d3dhM2VnQ0V2RnE5N3FHNW1CWWxDa0NQdU9JYkxsTVF3UWdCWVE2WmhOY0haOHloCkFBUTVBa0JPdE1OTDRjMFdKcTZTUDRteUtGQlpXeEI4VHdaSTRObExHRi9BbEJxZHYxR2ZSU2EvQkdFUTZiMmQKdS9QbUJOMThxRUZnQW9EczlFZDdueFpyUTlvaEFrQVYyRzgvQ0g1b0dXeTZPU0NSUVYzV1RpN2JxZUtrak5uMgp1SStJUCt1S2FxTVlZZlJmOW5XZ2JhcUFjUk42cVR5Skl4ZW1ZU25sTk1aelpyOUsrMkJwQWtCWlNxZEl0S2VUCnlYWWxJdW1IcVQ0RGhKalk1bnVCS3JjQ2tWSCtScXh5VkQxZGs4dGJQbm9wNTJuWTV3ZVk2UzZZSUhkeGJqN2UKcXJ4OE54RjhaSnNCCi0tLS0tRU5EIFBSSVZBVEUgS0VZLS0tLS0K", 
                "user.crt": "LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCk1JSUI4akNDQVZzQ0FnUG9NQTBHQ1NxR1NJYjNEUUVCQlFVQU1FRXhDekFKQmdOVkJBWVRBbFZUTVJZd0ZBWUQKVlFRS0RBMURhWE5qYnlCVGVYTjBaVzF6TVJvd0dBWURWUVFEREJGVmMyVnlJRzE1WDJOc2RYTjBaWEpmTVRBZQpGdzB4T0RBek1ERXhPVFU0TWpaYUZ3MHlPREF5TWpnd056VTRNalphTUVFeEN6QUpCZ05WQkFZVEFsVlRNUll3CkZBWURWUVFLREExRGFYTmpieUJUZVhOMFpXMXpNUm93R0FZRFZRUUREQkZWYzJWeUlHMTVYMk5zZFhOMFpYSmYKTVRDQm56QU5CZ2txaGtpRzl3MEJBUUVGQUFPQmpRQXdnWWtDZ1lFQTJYeitRQXlyakd4ckNKQThGbmtLYjVuKwpHZnJSS0NKRW1tU1pIWHlscUJWNUpkeWdYMlE3VUdIemVuMElBQ3BlTlpyTnpZZVpoUFpqTElsSlJwUzBYaUFlCkYzdFBWSzFFdEZmd094VmVrRUdCdUc5WC9JaGFRWUc1cGpHU0dLNEF4cUVyRTE5bkprSlAybmpOQTVoWkgyQjgKSFVObzdLbnVSYkNqUlhURGg2c0NBd0VBQVRBTkJna3Foa2lHOXcwQkFRVUZBQU9CZ1FEUUVKelo1YzNFQjd0Ugpnd055VG1Gd3hWbkZlRHJ0ZXd4U1VWdENYS1EwUnVsRGhvandUTlJGL1RSWDJTZU1Xa0NtdzB3K0N1NDhxYlF6CnRtUkIyVW40NGk0OG1EWlh5VHZ6MUlhMzJXNEpXNU5ZMmg3RDdJNERQZy9lZWpxQU0yRHArWVJqRkc0QW9wVXEKSEZwL1JRU3NHTURNZnJ5UDRxVUszYkY5UVJTNGdRPT0KLS0tLS1FTkQgQ0VSVElGSUNBVEUtLS0tLQo="
            }, 
            "apiVersion": "v1", 
            "metadata": {
                "labels": {
                    "aci-containers-config-version": "5d1daa9d-a8f2-496e-a414-8c0413991bfa"
                }, 
                "namespace": "kube-system", 
                "name": "aci-user-cert"
            }
        }, 
        {
            "kind": "ServiceAccount", 
            "apiVersion": "v1", 
            "metadata": {
                "labels": {
                    "aci-containers-config-version": "5d1daa9d-a8f2-496e-a414-8c0413991bfa"
                }, 
                "namespace": "kube-system", 
                "name": "aci-containers-controller"
            }
        }, 
        {
            "kind": "ServiceAccount", 
            "apiVersion": "v1", 
            "metadata": {
                "labels": {
                    "aci-containers-config-version": "5d1daa9d-a8f2-496e-a414-8c0413991bfa"
                }, 
                "namespace": "kube-system", 
                "name": "aci-containers-host-agent"
            }
        }, 
        {
            "rules": [
                {
                    "apiGroups": [
                        ""
                    ], 
                    "verbs": [
                        "list", 
                        "watch", 
                        "get"
                    ], 
                    "resources": [
                        "nodes", 
                        "namespaces", 
                        "pods", 
                        "endpoints", 
                        "services"
                    ]
                }, 
                {
                    "apiGroups": [
                        "networking.k8s.io"
                    ], 
                    "verbs": [
                        "list", 
                        "watch", 
                        "get"
                    ], 
                    "resources": [
                        "networkpolicies"
                    ]
                }, 
                {
                    "apiGroups": [
                        "extensions"
                    ], 
                    "verbs": [
                        "list", 
                        "watch", 
                        "get"
                    ], 
                    "resources": [
                        "deployments", 
                        "replicasets"
                    ]
                }, 
                {
                    "apiGroups": [
                        ""
                    ], 
                    "verbs": [
                        "update"
                    ], 
                    "resources": [
                        "pods", 
                        "nodes", 
                        "services/status"
                    ]
                }
            ], 
            "kind": "ClusterRole", 
            "apiVersion": "rbac.authorization.k8s.io/v1beta1", 
            "metadata": {
                "labels": {
                    "network-plugin": "aci-containers", 
                    "aci-containers-config-version": "5d1daa9d-a8f2-496e-a414-8c0413991bfa"
                }, 
                "name": "aci-containers:controller"
            }
        }, 
        {
            "rules": [
                {
                    "apiGroups": [
                        ""
                    ], 
                    "verbs": [
                        "list", 
                        "watch", 
                        "get"
                    ], 
                    "resources": [
                        "nodes", 
                        "pods", 
                        "endpoints", 
                        "services"
                    ]
                }
            ], 
            "kind": "ClusterRole", 
            "apiVersion": "rbac.authorization.k8s.io/v1beta1", 
            "metadata": {
                "labels": {
                    "network-plugin": "aci-containers", 
                    "aci-containers-config-version": "5d1daa9d-a8f2-496e-a414-8c0413991bfa"
                }, 
                "name": "aci-containers:host-agent"
            }
        }, 
        {
            "roleRef": {
                "apiGroup": "rbac.authorization.k8s.io", 
                "kind": "ClusterRole", 
                "name": "aci-containers:controller"
            }, 
            "kind": "ClusterRoleBinding", 
            "subjects": [
                {
                    "kind": "ServiceAccount", 
                    "namespace": "kube-system", 
                    "name": "aci-containers-controller"
                }
            ], 
            "apiVersion": "rbac.authorization.k8s.io/v1beta1", 
            "metadata": {
                "labels": {
                    "aci-containers-config-version": "5d1daa9d-a8f2-496e-a414-8c0413991bfa"
                }, 
                "name": "aci-containers:controller"
            }
        }, 
        {
            "roleRef": {
                "apiGroup": "rbac.authorization.k8s.io", 
                "kind": "ClusterRole", 
                "name": "aci-containers:host-agent"
            }, 
            "kind": "ClusterRoleBinding", 
            "subjects": [
                {
                    "kind": "ServiceAccount", 
                    "namespace": "kube-system", 
                    "name": "aci-containers-host-agent"
                }
            ], 
            "apiVersion": "rbac.authorization.k8s.io/v1beta1", 
            "metadata": {
                "labels": {
                    "aci-containers-config-version": "5d1daa9d-a8f2-496e-a414-8c0413991bfa"
                }, 
                "name": "aci-containers:host-agent"
            }
        }, 
        {
            "kind": "DaemonSet", 
            "spec": {
                "updateStrategy": {
                    "type": "RollingUpdate"
                }, 
                "template": {
                    "spec": {
                        "serviceAccountName": "aci-containers-host-agent", 
                        "hostNetwork": true, 
                        "restartPolicy": "Always", 
                        "containers": [
                            {
                                "livenessProbe": {
                                    "httpGet": {
                                        "path": "/status", 
                                        "port": 8090
                                    }
                                }, 
                                "securityContext": {
                                    "capabilities": {
                                        "add": [
                                            "SYS_ADMIN", 
                                            "NET_ADMIN"
                                        ]
                                    }
                                }, 
                                "name": "aci-containers-host", 
                                "image": "noiro/aci-containers-host:1.7r86", 
                                "volumeMounts": [
                                    {
                                        "mountPath": "/mnt/cni-bin", 
                                        "name": "cni-bin"
                                    }, 
                                    {
                                        "mountPath": "/mnt/cni-conf", 
                                        "name": "cni-conf"
                                    }, 
                                    {
                                        "mountPath": "/usr/local/var", 
                                        "name": "hostvar"
                                    }, 
                                    {
                                        "mountPath": "/run", 
                                        "name": "hostrun"
                                    }, 
                                    {
                                        "mountPath": "/usr/local/run", 
                                        "name": "hostrun"
                                    }, 
                                    {
                                        "mountPath": "/usr/local/etc/opflex-agent-ovs/base-conf.d", 
                                        "name": "opflex-hostconfig-volume"
                                    }, 
                                    {
                                        "mountPath": "/usr/local/etc/aci-containers/", 
                                        "name": "host-config-volume"
                                    }
                                ], 
                                "env": [
                                    {
                                        "valueFrom": {
                                            "fieldRef": {
                                                "fieldPath": "spec.nodeName"
                                            }
                                        }, 
                                        "name": "KUBERNETES_NODE_NAME"
                                    }
                                ], 
                                "imagePullPolicy": "Always"
                            }, 
                            {
                                "volumeMounts": [
                                    {
                                        "mountPath": "/usr/local/var", 
                                        "name": "hostvar"
                                    }, 
                                    {
                                        "mountPath": "/run", 
                                        "name": "hostrun"
                                    }, 
                                    {
                                        "mountPath": "/usr/local/run", 
                                        "name": "hostrun"
                                    }, 
                                    {
                                        "mountPath": "/usr/local/etc/opflex-agent-ovs/base-conf.d", 
                                        "name": "opflex-hostconfig-volume"
                                    }, 
                                    {
                                        "mountPath": "/usr/local/etc/opflex-agent-ovs/conf.d", 
                                        "name": "opflex-config-volume"
                                    }
                                ], 
                                "image": "noiro/opflex:1.7r60", 
                                "securityContext": {
                                    "capabilities": {
                                        "add": [
                                            "NET_ADMIN"
                                        ]
                                    }
                                }, 
                                "name": "opflex-agent", 
                                "imagePullPolicy": "Always"
                            }, 
                            {
                                "name": "mcast-daemon", 
                                "image": "noiro/opflex:1.7r60", 
                                "args": [
                                    "/usr/local/bin/launch-mcastdaemon.sh"
                                ], 
                                "volumeMounts": [
                                    {
                                        "mountPath": "/usr/local/var", 
                                        "name": "hostvar"
                                    }, 
                                    {
                                        "mountPath": "/run", 
                                        "name": "hostrun"
                                    }, 
                                    {
                                        "mountPath": "/usr/local/run", 
                                        "name": "hostrun"
                                    }
                                ], 
                                "command": [
                                    "/bin/sh"
                                ], 
                                "imagePullPolicy": "Always"
                            }
                        ], 
                        "volumes": [
                            {
                                "hostPath": {
                                    "path": "/opt"
                                }, 
                                "name": "cni-bin"
                            }, 
                            {
                                "hostPath": {
                                    "path": "/etc"
                                }, 
                                "name": "cni-conf"
                            }, 
                            {
                                "hostPath": {
                                    "path": "/var"
                                }, 
                                "name": "hostvar"
                            }, 
                            {
                                "hostPath": {
                                    "path": "/run"
                                }, 
                                "name": "hostrun"
                            }, 
                            {
                                "configMap": {
                                    "items": [
                                        {
                                            "path": "host-agent.conf", 
                                            "key": "host-agent-config"
                                        }
                                    ], 
                                    "name": "aci-containers-config"
                                }, 
                                "name": "host-config-volume"
                            }, 
                            {
                                "emptyDir": {
                                    "medium": "Memory"
                                }, 
                                "name": "opflex-hostconfig-volume"
                            }, 
                            {
                                "configMap": {
                                    "items": [
                                        {
                                            "path": "local.conf", 
                                            "key": "opflex-agent-config"
                                        }
                                    ], 
                                    "name": "aci-containers-config"
                                }, 
                                "name": "opflex-config-volume"
                            }
                        ], 
                        "hostIPC": true, 
                        "tolerations": [
                            {
                                "key": "CriticalAddonsOnly"
                            }, 
                            {
                                "effect": "NoSchedule", 
                                "key": "node-role.kubernetes.io/master"
                            }
                        ], 
                        "hostPID": true
                    }, 
                    "metadata": {
                        "labels": {
                            "network-plugin": "aci-containers", 
                            "name": "aci-containers-host"
                        }, 
                        "annotations": {
                            "scheduler.alpha.kubernetes.io/critical-pod": ""
                        }
                    }
                }, 
                "selector": {
                    "matchLabels": {
                        "network-plugin": "aci-containers", 
                        "name": "aci-containers-host"
                    }
                }
            }, 
            "apiVersion": "extensions/v1beta1", 
            "metadata": {
                "labels": {
                    "network-plugin": "aci-containers", 
                    "aci-containers-config-version": "5d1daa9d-a8f2-496e-a414-8c0413991bfa"
                }, 
                "namespace": "kube-system", 
                "name": "aci-containers-host"
            }
        }, 
        {
            "kind": "DaemonSet", 
            "spec": {
                "updateStrategy": {
                    "type": "RollingUpdate"
                }, 
                "template": {
                    "spec": {
                        "serviceAccountName": "aci-containers-host-agent", 
                        "hostNetwork": true, 
                        "restartPolicy": "Always", 
                        "containers": [
                            {
                                "livenessProbe": {
                                    "exec": {
                                        "command": [
                                            "/usr/local/bin/liveness-ovs.sh"
                                        ]
                                    }
                                }, 
                                "securityContext": {
                                    "capabilities": {
                                        "add": [
                                            "NET_ADMIN", 
                                            "SYS_MODULE", 
                                            "SYS_NICE", 
                                            "IPC_LOCK"
                                        ]
                                    }
                                }, 
                                "name": "aci-containers-openvswitch", 
                                "image": "noiro/openvswitch:1.7r24", 
                                "volumeMounts": [
                                    {
                                        "mountPath": "/usr/local/var", 
                                        "name": "hostvar"
                                    }, 
                                    {
                                        "mountPath": "/run", 
                                        "name": "hostrun"
                                    }, 
                                    {
                                        "mountPath": "/usr/local/run", 
                                        "name": "hostrun"
                                    }, 
                                    {
                                        "mountPath": "/usr/local/etc", 
                                        "name": "hostetc"
                                    }, 
                                    {
                                        "mountPath": "/lib/modules", 
                                        "name": "hostmodules"
                                    }
                                ], 
                                "env": [
                                    {
                                        "name": "OVS_RUNDIR", 
                                        "value": "/usr/local/var/run/openvswitch"
                                    }
                                ], 
                                "imagePullPolicy": "Always"
                            }
                        ], 
                        "volumes": [
                            {
                                "hostPath": {
                                    "path": "/etc"
                                }, 
                                "name": "hostetc"
                            }, 
                            {
                                "hostPath": {
                                    "path": "/var"
                                }, 
                                "name": "hostvar"
                            }, 
                            {
                                "hostPath": {
                                    "path": "/run"
                                }, 
                                "name": "hostrun"
                            }, 
                            {
                                "hostPath": {
                                    "path": "/lib/modules"
                                }, 
                                "name": "hostmodules"
                            }
                        ], 
                        "hostIPC": true, 
                        "tolerations": [
                            {
                                "key": "CriticalAddonsOnly"
                            }, 
                            {
                                "effect": "NoSchedule", 
                                "key": "node-role.kubernetes.io/master"
                            }
                        ], 
                        "hostPID": true
                    }, 
                    "metadata": {
                        "labels": {
                            "network-plugin": "aci-containers", 
                            "name": "aci-containers-openvswitch"
                        }, 
                        "annotations": {
                            "scheduler.alpha.kubernetes.io/critical-pod": ""
                        }
                    }
                }, 
                "selector": {
                    "matchLabels": {
                        "network-plugin": "aci-containers", 
                        "name": "aci-containers-openvswitch"
                    }
                }
            }, 
            "apiVersion": "extensions/v1beta1", 
            "metadata": {
                "labels": {
                    "network-plugin": "aci-containers", 
                    "aci-containers-config-version": "5d1daa9d-a8f2-496e-a414-8c0413991bfa"
                }, 
                "namespace": "kube-system", 
                "name": "aci-containers-openvswitch"
            }
        }, 
        {
            "kind": "Deployment", 
            "spec": {
                "strategy": {
                    "type": "Recreate"
                }, 
                "selector": {
                    "matchLabels": {
                        "network-plugin": "aci-containers", 
                        "name": "aci-containers-controller"
                    }
                }, 
                "template": {
                    "spec": {
                        "volumes": [
                            {
                                "secret": {
                                    "secretName": "aci-user-cert"
                                }, 
                                "name": "aci-user-cert-volume"
                            }, 
                            {
                                "configMap": {
                                    "items": [
                                        {
                                            "path": "controller.conf", 
                                            "key": "controller-config"
                                        }
                                    ], 
                                    "name": "aci-containers-config"
                                }, 
                                "name": "controller-config-volume"
                            }
                        ], 
                        "tolerations": [
                            {
                                "key": "CriticalAddonsOnly"
                            }
                        ], 
                        "hostNetwork": true, 
                        "serviceAccountName": "aci-containers-controller", 
                        "containers": [
                            {
                                "image": "noiro/aci-containers-controller:1.7r86", 
                                "volumeMounts": [
                                    {
                                        "mountPath": "/usr/local/etc/aci-containers/", 
                                        "name": "controller-config-volume"
                                    }, 
                                    {
                                        "mountPath": "/usr/local/etc/aci-cert/", 
                                        "name": "aci-user-cert-volume"
                                    }
                                ], 
                                "livenessProbe": {
                                    "httpGet": {
                                        "path": "/status", 
                                        "port": 8091
                                    }
                                }, 
                                "name": "aci-containers-controller", 
                                "imagePullPolicy": "Always"
                            }
                        ]
                    }, 
                    "metadata": {
                        "labels": {
                            "network-plugin": "aci-containers", 
                            "name": "aci-containers-controller"
                        }, 
                        "namespace": "kube-system", 
                        "annotations": {
                            "scheduler.alpha.kubernetes.io/critical-pod": ""
                        }, 
                        "name": "aci-containers-controller"
                    }
                }, 
                "replicas": 1
            }, 
            "apiVersion": "extensions/v1beta1", 
            "metadata": {
                "labels": {
                    "network-plugin": "aci-containers", 
                    "name": "aci-containers-controller", 
                    "aci-containers-config-version": "5d1daa9d-a8f2-496e-a414-8c0413991bfa"
                }, 
                "namespace": "kube-system", 
                "name": "aci-containers-controller"
            }
        }
    ], 
    "allocator_state": {
        "net_config.service_vlan": 2121, 
        "net_config.node_svc_subnet": "10.5.0.0/24", 
        "net_config.pod_subnet": "10.50.0.1/16", 
        "aci_config.vmm_domain.mcast_range.end": "225.32.255.255", 
        "net_config.kubeapi_vlan": 2120, 
        "aci_config.system_id": "my_cluster_1", 
        "aci_config.vmm_domain.mcast_range.start": "225.32.1.1"
    }
}
```

Make sure that the `my_cluster_1` tenant is created in the "Tenants" tab in the ACI APIC fabric at https://10.23.231.5.

HTTP status code `200` when creation of ACI configs is in progress:

```
{
    "message": "Creation of ACI configs for cluster still in progress... Re-try after few seconds."
}
```

**NOTE:** After doing `HTTP POST` to endpoint `/api/v1/acc_provision_create`, if endpoint `/api/v1/acc_provision_status` never returns the ACI CNI as json, then it means the creation of ACI configs **failed**, and the client **must re-try** creating the ACI configs again by doing `HTTP POST` again to the endpoint `/api/v1/acc_provision_create` and then do `HTTP GET` from endpoint `/api/v1/acc_provision_status` again to get the ACI CNI as json in the response.

#### Request format for `/api/v1/acc_provision_delete`

Example below is for:

```
ccp_cluster_name : my_cluster_1
aci_username : admin
aci_password : cisco123!
```

```
{
    "aci_username": "admin",
    "ccp_cluster_name": "my_cluster_1",
    "aci_password": "cisco123!"
}

```

#### Response format for `/api/v1/acc_provision_delete`

HTTP status code `202`:

```
{
    "response": "Request accepted to delete ACI configs. Use http endpoint /api/v1/acc_provision_status to get the status."
}
```

HTTP status code `404` from `HTTP GET` from endpoint `/api/v1/acc_provision_status` when the ACI configs are successfully deleted:

```
{
    "error": "ERROR: ACI CNI not found for cluster. Use http endpoint /api/v1/acc_provision_create to create (POST) configs on ACI first, and then use this endpoint to get the ACI CNI for the cluster. If http endpoint /api/v1/acc_provision_delete was used to delete the ACI configs, then this message means the deletion was successful."
}
```

Make sure that the `my_cluster_1` tenant is deleted in the "Tenants" tab in the ACI APIC fabric at https://10.23.231.5.

## `curl` (`HTTP GET` from endpoint `/`) to see the REST API operations supported and versions

The following `curl` (`HTTP GET` from endpoint `/`) command shows the REST API operations supported and versions:

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

`git_sha1` above is the git SHA1 of the latest commit in this repo and `version` above is the version of `acc-provision` tool.
