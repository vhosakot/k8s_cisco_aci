#!/usr/bin/python

# Copyright 2018 Cisco Systems
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import configparser
import etcd3
import iptools
import json
from netaddr import *
import os
import socket
import struct
import time


def increment_ip(ip, by=1):
    if by <= 0:
        raise ValueError("increment value must be >= 0")

    try:
        i = struct.unpack('!I', socket.inet_aton(ip))[0] + by
        return str(socket.inet_ntoa(struct.pack('!I', i)))
    except:
        raise InvalidIPError("IP %s can't be incremented by %d" % (ip, by))


def generate_next_subnet(subnet, network="/24"):
    """
    generate_next_subnet converts '10.0.0.0/24' into '10.1.0.0/24' and '10.255.0.0/24' into '11.0.0.0/24'.
    network can be specified if the /24 default is not desired
    """

    # TODO: this will fail if 255.255.0.0 is the input and we try to generate the next ip.
    #       we should check at startup that the specified subnet starting points allow
    #       for vlan_max - vlan_min subnets to be allocated.
    ip = increment_ip(str(IPNetwork(subnet).ip), 2**16)

    return ip + network


def start_and_end_addresses_for_mcast_range(subnet):
    r = iptools.IpRangeList(subnet)

    s = r.ips[0][0]
    e = r.ips[0][-1]

    # use x.y.1.1 instead of x.y.0.0 for start address
    s = increment_ip(s, 2**8 + 1)

    return s, e


class TenantAlreadyExistsError(Exception):
    pass


class InsufficientVLANsAvailableError(Exception):
    pass


class NoServiceSubnetsAvailableError(Exception):
    pass


class NoMulticastRangesAvailableError(Exception):
    pass


class TenantDoesNotExistError(Exception):
    pass


class InvalidIPError(Exception):
    pass


class InvalidNameError(Exception):
    pass


class NoPodSubnetsAvailableError(Exception):
    pass


class Allocator:

    DB_KEY = "/ccp_aci_service"
    LOCK_NAME = "ccp_aci_service_lock"

    KUBEAPI_VLAN_KEY = "net_config.kubeapi_vlan"
    SERVICE_VLAN_KEY = "net_config.service_vlan"
    MULTICAST_RANGE_START_KEY = "aci_config.vmm_domain.mcast_range.start"
    MULTICAST_RANGE_END_KEY = "aci_config.vmm_domain.mcast_range.end"
    SERVICE_SUBNET_KEY = "net_config.node_svc_subnet"
    POD_SUBNET_KEY = "net_config.pod_subnet"

    def __init__(self, etcd_client, config_file="aci.conf", **kwargs):
        aci_config = self._get_aci_config(config_file)

        self.DEFAULT_VLAN_MIN = int(aci_config['DEFAULT']['DEFAULT_VLAN_MIN'])
        # DEFAULT_VLAN_MAX's maximum value is 4095
        self.DEFAULT_VLAN_MAX = int(aci_config['DEFAULT']['DEFAULT_VLAN_MAX'])
        self.DEFAULT_MULTICAST_RANGE = aci_config['DEFAULT'][
            'DEFAULT_MULTICAST_RANGE']
        self.DEFAULT_SERVICE_SUBNET = aci_config['DEFAULT'][
            'DEFAULT_SERVICE_SUBNET']
        # DEFAULT_POD_SUBNET has to end with .1
        self.DEFAULT_POD_SUBNET = aci_config['DEFAULT']['DEFAULT_POD_SUBNET']

        self.etcd_client = etcd_client

        self.VLAN_MIN = kwargs.get("vlan_min", self.DEFAULT_VLAN_MIN)
        self.VLAN_MAX = kwargs.get("vlan_max", self.DEFAULT_VLAN_MAX)

        # validate that vlan ids fall inside an acceptable range
        if self.VLAN_MIN < 1:
            raise ValueError("vlan_min must be >= 1 (got %d)" % self.VLAN_MIN)

        if self.VLAN_MAX > 4094:
            raise ValueError(
                "vlan_max must be <= 4094 (got %d)" % self.VLAN_MAX)

        # a reservation requires 2 vlan ids minimum
        if self.VLAN_MIN + 1 > self.VLAN_MAX:
            raise ValueError(
                "vlan_max must be at least 1 id higher than vlan_min (got %d and %d respectively)"
                % (self.VLAN_MIN, self.VLAN_MAX))

        self.MAX_VLANS = self.VLAN_MAX - self.VLAN_MIN

        self.MULTICAST_RANGE = kwargs.get("multicast_range",
                                          self.DEFAULT_MULTICAST_RANGE)
        self.SERVICE_SUBNET = kwargs.get("service_subnet",
                                         self.DEFAULT_SERVICE_SUBNET)
        self.POD_SUBNET = kwargs.get("pod_subnet", self.DEFAULT_POD_SUBNET)

        # TODO: ensure that there is sufficient distance between multicast range start and 255.255.0.0 to
        #       allow MAX_VLANS octets to be assigned

        # TODO: ensure that there is sufficient distance between multicast range start and service subnet
        #       to allow MAX_VLANS octets to be assigned.
        # TODO: do we need to support both ways? (a > b and b > a)
        # TODO: another edge case, both set to the same thing (lol)

    # function to read ACI configurations from config_file
    def _get_aci_config(self, config_file):
        if not os.path.exists(config_file):
            # set defaults if config_file is not found
            config = {'DEFAULT': {}}
            config['DEFAULT']['DEFAULT_VLAN_MIN'] = 2120

            # DEFAULT_VLAN_MAX's maximum value is 4095
            config['DEFAULT']['DEFAULT_VLAN_MAX'] = 4000

            config['DEFAULT']['DEFAULT_MULTICAST_RANGE'] = "225.32.0.0/16"
            config['DEFAULT']['DEFAULT_SERVICE_SUBNET'] = "10.5.0.0/24"

            # DEFAULT_POD_SUBNET has to end with .1
            config['DEFAULT']['DEFAULT_POD_SUBNET'] = "10.50.0.1/16"

            return config

        else:
            # read ACI configurations from config_file
            config = configparser.ConfigParser()
            config.read(config_file)
            return config

    def reserve(self, tenant_name):
        """
        reserve takes a (hopefully locked) etcd client, generates a unique set of
        vlan ids and subnets for the named tenant, stores that info into etcd, and
        returns the generated set.
        """

        with self.etcd_client.lock(self.LOCK_NAME):
            return self.__locked_reserve(tenant_name)

    def __locked_reserve(self, tenant_name):

        if tenant_name == '' or ' ' in tenant_name:
            raise InvalidNameError(
                "name must be one or more characters without spaces")

        # 1. load state from db
        state = self.load_from_db()

        if tenant_name in state:
            raise TenantAlreadyExistsError(
                "tenant " + tenant_name + " already exists")

        # 2. find the next two unused vlan ids
        existing_vlan_ids = []

        for key in state:
            existing_vlan_ids.append(state[key][self.KUBEAPI_VLAN_KEY])
            existing_vlan_ids.append(state[key][self.SERVICE_VLAN_KEY])

        unused_vlan_ids = set(range(
            self.VLAN_MIN, self.VLAN_MAX + 1)) - set(existing_vlan_ids)
        unused_vlan_ids = sorted(list(unused_vlan_ids))

        if len(unused_vlan_ids) < 2:
            raise InsufficientVLANsAvailableError(
                "unable to allocate 2 vlan ids, only %d ids available" %
                len(unused_vlan_ids))

        # 3. find an unused service subnet
        existing_svc_subnets = []

        for key in state:
            existing_svc_subnets.append(state[key][self.SERVICE_SUBNET_KEY])

        svc_subnet = self.SERVICE_SUBNET
        svc_subnet_found = False

        for i in range(0, self.MAX_VLANS):
            if svc_subnet in existing_svc_subnets:
                try:
                    svc_subnet = generate_next_subnet(svc_subnet)
                except InvalidIPError:
                    raise NoServiceSubnetsAvailableError()

                continue
            else:
                svc_subnet_found = True
                break

        if not svc_subnet_found:
            raise NoServiceSubnetsAvailableError(
                "unable to find a free service subnet, %d are already allocated"
                % len(existing_svc_subnets))

        # 4. find an unused multicast range
        existing_mcast_ranges = []

        for key in state:
            parts = state[key][self.MULTICAST_RANGE_START_KEY].split('.')
            r = parts[0] + "." + parts[1] + ".0.0/16"
            existing_mcast_ranges.append(r)

        mcast_range = self.MULTICAST_RANGE
        mcast_range_found = False

        for i in range(0, self.MAX_VLANS):
            if mcast_range in existing_mcast_ranges:
                try:
                    mcast_range = generate_next_subnet(mcast_range, "/16")
                except InvalidIPError:
                    raise NoMulticastRangesAvailableError()

                continue
            else:
                mcast_range_found = True
                break

        if not mcast_range_found:
            raise NoMulticastRangesAvailableError(
                "unable to find a free multicast range, %d are already allocated"
                % len(existing_mcast_ranges))

        mcast_range_start, mcast_range_end = start_and_end_addresses_for_mcast_range(
            mcast_range)

        # 5. find an unused pod subnet
        existing_pod_subnets = []

        for key in state:
            existing_pod_subnets.append(state[key][self.POD_SUBNET_KEY])

        pod_subnet = self.POD_SUBNET
        pod_subnet_found = False

        for i in range(0, self.MAX_VLANS):
            if pod_subnet in existing_pod_subnets:
                try:
                    pod_subnet = generate_next_subnet(pod_subnet, "/16")
                except InvalidIPError:
                    raise NoPodSubnetsAvailableError()

                continue
            else:
                pod_subnet_found = True
                break

        if not pod_subnet_found:
            raise NoServiceSubnetsAvailableError(
                "unable to find a free service subnet, %d are already allocated"
                % len(existing_svc_subnets))

        # 6. update the state object, convert to json, store in db
        state[tenant_name] = {
            'aci_config.system_id': tenant_name,
            self.KUBEAPI_VLAN_KEY: unused_vlan_ids.pop(0),
            self.SERVICE_VLAN_KEY: unused_vlan_ids.pop(0),
            self.SERVICE_SUBNET_KEY: svc_subnet,
            self.MULTICAST_RANGE_START_KEY: mcast_range_start,
            self.MULTICAST_RANGE_END_KEY: mcast_range_end,
            self.POD_SUBNET_KEY: pod_subnet
        }

        self.store_in_db(state)  # TODO: check result or just let it raise?

        # 6. return state object
        return state[tenant_name]

    def free(self, tenant_name):
        with self.etcd_client.lock(self.LOCK_NAME):
            return self.__locked_free(tenant_name)

    def __locked_free(self, tenant_name):
        # 1. load state from db
        state = self.load_from_db()

        # 2. delete the tenant key
        if tenant_name in state:
            state.pop(tenant_name, None)
        else:
            raise TenantDoesNotExistError(
                "tenant " + tenant_name + " does not exist")

        # 3. store in db
        self.store_in_db(state)  # TODO: check result

    def get(self, tenant_name):
        with self.etcd_client.lock(self.LOCK_NAME):
            return self.__locked_get(tenant_name)

    def __locked_get(self, tenant_name):
        return self.load_from_db().get(tenant_name, {})

    def load_from_db(self):
        val = self.etcd_client.get(self.DB_KEY)[0]

        if val:
            return json.loads(val)
        else:
            return {}

    def store_in_db(self, state):
        # TODO: check that this was successful and raise if not
        self.etcd_client.put(self.DB_KEY, json.dumps(state))


# if __name__ == "__main__":
#    etcd = etcd3.client()

#    a = Allocator(etcd)
#    a.get("tenant1") # doesn't exist
#    a.reserve("tenant1")
#    a.reserve("tenant2")
#    a.reserve("tenant3")
#    a.get("tenant1") # exists
#    a.free("tenant1")
#    a.free("tenant2")
#    a.free("tenant3")
#    a.get("tenant1") # doesn't exist
