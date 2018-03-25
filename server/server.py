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

import allocator
from datetime import datetime
import json
import logging
import subprocess
import threading
import time
import os
import yaml

lock = threading.Lock()


class CcpAciServer(object):
    def __init__(self, http_request, etcd_client, config_file="aci.conf"):
        self.http_request = http_request
        self.acc_provision_input_YAML = ''.join([
            "acc_provision_input_", http_request["ccp_cluster_name"], ".yaml"
        ])
        self.aci_cni_output_YAML = ''.join(
            ["aci_cni_deployment_", http_request["ccp_cluster_name"], ".yaml"])
        self.etcd_client = etcd_client
        self.db_key = self._generate_db_key()
        self.etcd_lock_name = "acc_provision_status_lock"
        self.aci_flavor = self._get_aci_flavor()
        self.config_file = config_file

    # function to generate etcd key for creation_status
    def _generate_db_key(self):
        L = [
            "/acc_provision_status", self.http_request["ccp_cluster_name"],
            "ccp"
        ]
        # key format in etcd is:
        # /acc_provision_status__<cluster name>__ccp
        return '__'.join(L)

    # function to get the ACI flavor from k8s version
    def _get_aci_flavor(self):

        if "k8s_version" in self.http_request:
            if "1.7" in self.http_request["k8s_version"]:
                return "kubernetes-1.7"
            elif "1.8" in self.http_request["k8s_version"]:
                return "kubernetes-1.8"
            elif "1.9" in self.http_request["k8s_version"]:
                return "kubernetes-1.9"

        elif self.get_from_etcd()[0] is not None:
            # return aci_flavor from etcd for "delete" and "status" operations
            try:
                return json.loads(self.get_from_etcd()[0])["aci_flavor"]
            except:
                pass

    # this function checks if the cluster name (self.db_key) already exists in etcd
    def cluster_name_is_duplicate(self):
        # delete expired and failed creations in progress if any
        self._delete_expired_creations_in_progress()

        if self.get_from_etcd()[0] is not None:
            return True

    # static function to validate fields in HTTP payload
    @staticmethod
    def validate_http_payload(http_request, create=False):

        if create:
            if "k8s_version" not in http_request or \
               "ccp_cluster_name" not in http_request or \
               "aci_username" not in http_request or \
               "aci_password" not in http_request or \
               "aci_input_json" not in http_request:
                print "\nERROR: validate_http_payload failed\n"
                return False

            if "1.7" not in http_request["k8s_version"] and \
               "1.8" not in http_request["k8s_version"] and \
               "1.9" not in http_request["k8s_version"]:
                print "\nERROR: Invalid Kubernetes version:",\
                       http_request["k8s_version"], "\n"
                return False

        else:
            if "ccp_cluster_name" not in http_request or \
               "aci_username" not in http_request or \
               "aci_password" not in http_request:
                print "\nERROR: validate_http_payload failed\n"
                return False

        return True

    # function that gets unique VLAN, subnet and IP from server/allocator.py
    # for each tenant cluster and updates the ACI input json used to
    # create configs on ACI
    def update_aci_input_json_for_cluster(self):
        aci_allocator = allocator.Allocator(self.etcd_client, self.config_file)
        per_cluster_state = aci_allocator.get(
            self.http_request["ccp_cluster_name"])
        if per_cluster_state == {}:
            per_cluster_state = aci_allocator.reserve(
                self.http_request["ccp_cluster_name"])

        # create dummy mcast_range key in the ACI input json before updating it
        self.http_request["aci_input_json"]["aci_config"]\
                         ["vmm_domain"]["mcast_range"] = \
                         {"start" : "", "end" : ""}

        for k in per_cluster_state.keys():
            aci_keys = k.split('.')
            if len(aci_keys) == 1:
                self.http_request["aci_input_json"]\
                    [aci_keys[0]] = per_cluster_state[k]
            elif len(aci_keys) == 2:
                self.http_request["aci_input_json"]\
                    [aci_keys[0]]\
                    [aci_keys[1]] = per_cluster_state[k]
            elif len(aci_keys) == 3:
                self.http_request["aci_input_json"]\
                    [aci_keys[0]]\
                    [aci_keys[1]]\
                    [aci_keys[2]] = per_cluster_state[k]
            elif len(aci_keys) == 4:
                self.http_request["aci_input_json"]\
                    [aci_keys[0]]\
                    [aci_keys[1]]\
                    [aci_keys[2]]\
                    [aci_keys[3]] = per_cluster_state[k]

    # function to convert input json to YAML file
    def convert_input_json_to_yaml_file(self):
        if os.path.exists(self.acc_provision_input_YAML):
            os.remove(self.acc_provision_input_YAML)

        f = open(self.acc_provision_input_YAML, "w")

        input_json = {}

        if "aci_input_json" in self.http_request:
            # get input_json from http payload for "create" operation
            input_json = self.http_request["aci_input_json"]

        elif self.get_from_etcd()[0] is not None:
            # get input_json from etcd for "delete" and "status" operations
            input_json = json.loads(self.get_from_etcd()[0])["aci_input_json"]

        f.write(yaml.safe_dump(input_json, default_flow_style=False))
        f.close()

    # function to get the ACI certificate and key file from etcd
    #
    # after creating configs on ACI, ACI sends back a certificate file
    # (user-<cluster name>.crt) and a key file (user-<cluster name>.key) and
    # they are needed and used when deleting configs on ACI. Without these
    # crt and key files, configs cannot be deleted on the ACI. If these crt
    # and key files are missing due to any reason, get them from etcd and
    # create these files so that they can be used to delete configs on ACI.
    #
    def get_aci_certs_from_etcd(self):
        crt_filename = "user-" + \
                   self.http_request["ccp_cluster_name"] + \
                   ".crt"
        if not os.path.exists(crt_filename):
            f = open(crt_filename, "w")
            f.write(json.loads(self.get_from_etcd()[0])["crt_file"])
            f.close()

        key_filename = "user-" + \
                   self.http_request["ccp_cluster_name"] + \
                   ".key"
        if not os.path.exists(key_filename):
            f = open(key_filename, "w")
            f.write(json.loads(self.get_from_etcd()[0])["key_file"])
            f.close()

    # function to retry the acc-provision command
    def run_command_and_retry(self, operation, retry_count=11):
        # retry loop
        for i in range(1, retry_count):

            # if create fails repeatedly, delete after create fails twice
            # as deleting will make the subsequent create succeed
            #
            # in other words, if create fails repeatedly, delete once in
            # three times as deleting will make the subsequent create succeed
            if operation == "create" and (i % 3) == 0:
                cmd = self._build_command("delete")
            else:
                cmd = self._build_command(operation)

            c = cmd.split()
            # don't print ACI username and password in logs
            c.remove(c[c.index('-u') + 1])
            c.remove(c[c.index('-p') + 1])

            print ''.join([
                datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'),
                " acc-provision command sent to ACI fabric", " (try ",
                str(i) + ")", "\n\n", ' '.join(c), "\n"
            ])

            # grab lock and run acc-provision command on ACI fabric
            global lock
            with lock:
                if not os.path.exists(self.acc_provision_input_YAML):
                    if "aci_input_json" in self.http_request:
                        # update ACI input json only for create operation
                        self.update_aci_input_json_for_cluster()
                    self.convert_input_json_to_yaml_file()

                result = self.run_command(cmd)
                # rate-limit multiple back-to-back requests to acc-provision
                time.sleep(3)

            # if create fails repeatedly, after deleting once in three times,
            # continue and do the subsequent create
            if operation == "create" and (i % 3) == 0:
                # sleep 3 seconds before trying the subsequent create
                time.sleep(3)
                continue

            if result is not None:
                print str(result)

            if operation == "create":
                if result is None or \
                   "kubectl apply -f aci_cni_deployment" not in result or \
                   not os.path.exists(self.aci_cni_output_YAML):
                    print "\nERROR: acc_provision_create failed (try " + str(
                        i) + ")", "\n"
                    if i < (retry_count - 1):
                        # sleep 3 seconds before trying to create again
                        time.sleep(3)

                        # return False if creation was successful in another parallel thread
                        if self.get_from_etcd()[0] is not None and \
                            json.loads(self.get_from_etcd()[0])["completed"]:
                            # no need to retry creating already-created configs
                            return False
                    else:
                        # all retries to create have failed at this point
                        print "ERROR: acc_provision_create failed after", str(
                            retry_count - 1), "retries"
                else:
                    # create succeeded
                    return True
            elif operation == "delete":
                if result is None:
                    print "\nERROR: acc_provision_delete failed (try " + str(
                        i) + ")", "\n"
                    if i < (retry_count - 1):
                        # sleep 3 seconds before trying to delete again
                        time.sleep(3)

                        # return False if deletion was successful in another parallel thread
                        if self.get_from_etcd()[0] is None:
                            # no need to retry deleting already-deleted configs
                            return False
                    else:
                        # all retries to delete have failed at this point
                        print "ERROR: acc_provision_delete failed after", str(
                            retry_count - 1), "retries"
                else:
                    # delete succeeded
                    return True

        # all retries to create/delete have failed, return False
        return False

    # static function to run a Linux command
    @staticmethod
    def run_command(cmd):
        try:
            cmd = "timeout 20 " + cmd
            p = subprocess.Popen(
                cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (output, err) = p.communicate()

            if p.returncode != 0:
                if err != "" and len(err) > 1 and err is not None:
                    print "\nERROR:", err
                raise Exception("Command failed with non-zero return code")

            if 'ERR:' in output or 'ERR:' in err:
                print output
                print err
                raise Exception("acc-provision command failed with errors")

            return ''.join([str(output), str(err)])
        except Exception as e:
            c = cmd.split()
            # don't print ACI username and password in logs
            if '-u' in c:
                c.remove(c[c.index('-u') + 1])
            if '-p' in c:
                c.remove(c[c.index('-p') + 1])
            print "\nERROR: The command \"" + ' '.join(c) + \
                  "\" failed with the following error: \n", type(e), str(e), "\n"
            logging.exception(e)

    # function to remove input and output YAML files
    def cleanup_files(self):
        if os.path.exists(self.acc_provision_input_YAML):
            os.remove(self.acc_provision_input_YAML)
        if hasattr(self, 'aci_cni_output_YAML') and os.path.exists(
                self.aci_cni_output_YAML):
            os.remove(self.aci_cni_output_YAML)

    # static function to get the git sha1 as the version
    @staticmethod
    def get_version():
        if os.path.exists("/ccp_aci_service_version"):
            return CcpAciServer.run_command("cat /ccp_aci_service_version")
        else:
            return CcpAciServer.run_command("cat ../ccp_aci_service_version")

    # function to convert ACI CNI deployment output YAML to list
    def get_response_list(self):
        f = open(self.aci_cni_output_YAML, "r")
        k8s_manifests = yaml.load_all(f)
        response = []
        for k8s_manifest in k8s_manifests:
            response.append(k8s_manifest)
        f.close()
        return response

    # function to get value of self.db_key from etcd
    def get_from_etcd(self):
        with self.etcd_client.lock(self.etcd_lock_name):
            return self.etcd_client.get(self.db_key)

    # function to put a dictionary as value of self.db_key into etcd
    def put_into_etcd(self, dict_value):
        with self.etcd_client.lock(self.etcd_lock_name):
            self.etcd_client.put(self.db_key, json.dumps(dict_value))

    # function to update creation_status value of self.db_key in etcd
    def update_creation_status_in_etcd(self, response):
        key_filename = "user-" + \
                   self.http_request["ccp_cluster_name"] + \
                   ".key"
        f = open(key_filename, "r")
        key_file = f.read()
        f.close()

        crt_filename = "user-" + \
                   self.http_request["ccp_cluster_name"] + \
                   ".crt"
        f = open(crt_filename, "r")
        crt_file = f.read()
        f.close()

        per_cluster_status = {
            "completed": True,
            "crt_file": crt_file,
            "key_file": key_file,
            "aci_input_json": self.http_request["aci_input_json"],
            "aci_flavor": self.aci_flavor,
            "output_aci_cni_yaml": response,
            "creation_start_time": 0.0,
            "key_name": self.db_key
        }
        self.put_into_etcd(per_cluster_status)

    # function to delete self.db_key in etcd
    def delete_from_etcd(self):
        with self.etcd_client.lock(self.etcd_lock_name):
            self.etcd_client.delete(self.db_key)

    # function to delete stale key for the cluster in etcd
    def delete_stale_key_in_etcd(self):
        prefix = ''.join([
            "/acc_provision_status__", self.http_request["ccp_cluster_name"],
            "__"
        ])
        with self.etcd_client.lock(self.etcd_lock_name):
            self.etcd_client.delete_prefix(prefix)

    # function to get the per-cluster ACI CNI if it exists in etcd
    def get_aci_cni_for_cluster_from_etcd(self):
        if self.get_from_etcd()[0] is None:
            return [False, False]
        elif not json.loads(self.get_from_etcd()[0])["completed"]:
            return ["", "Creation of ACI configs for cluster still in progress... "\
                   "Re-try after few seconds."]
        else:
            aci_cni_json = json.loads(
                self.get_from_etcd()[0])["output_aci_cni_yaml"]
            aci_allocator = allocator.Allocator(self.etcd_client,
                                                self.config_file)
            per_cluster_allocator_state = aci_allocator.get(
                self.http_request["ccp_cluster_name"])
            return [per_cluster_allocator_state, aci_cni_json]

    # function to build acc-provision command
    def _build_command(self, operation):
        if operation == "create":
            return ''.join([
                "acc-provision -a -c ", self.acc_provision_input_YAML, " -f ",
                self.aci_flavor, " ", "-o ", self.aci_cni_output_YAML,
                " --debug -u ", self.http_request["aci_username"], " ", "-p ",
                self.http_request["aci_password"]
            ])

        elif operation == "delete":
            return ''.join([
                "acc-provision -d -c ", self.acc_provision_input_YAML, " -f ",
                self.aci_flavor, " ", "--debug -u ",
                self.http_request["aci_username"], " ", "-p ",
                self.http_request["aci_password"]
            ])

    # function to delete expired and failed creations in progress
    # (default expiration time is 5 mins or 300 seconds)
    def _delete_expired_creations_in_progress(self, expiration_time=300):
        with self.etcd_client.lock("expiration_lock"):
            state = self.etcd_client.get_prefix("/acc_provision_status")
            for creation_status in state:
                c = json.loads(creation_status[0])
                creation_start_time = c["creation_start_time"]
                completed = c["completed"]
                if creation_start_time != 0.0 and \
                   not completed and \
                   (time.time() - creation_start_time) > expiration_time:
                    # delete expired creation status in progress for failed cluster
                    self.etcd_client.delete(c["key_name"])

                    # get cluster name from c["key_name"]
                    #
                    # format of c["key_name"] in etcd is:
                    # /acc_provision_status__<cluster name>__ccp
                    #
                    cluster_name = c["key_name"].split('__')
                    cluster_name.remove(cluster_name[0])
                    cluster_name.remove(cluster_name[len(cluster_name) - 1])
                    cluster_name = ''.join(cluster_name)

                    # delete expired allocator state for failed cluster
                    a = allocator.Allocator(self.etcd_client, self.config_file)
                    if a.get(cluster_name) != {}:
                        a.free(cluster_name)
                    print "\n", datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'),\
                          "Creation of ACI configs for cluser", cluster_name,\
                          "did not succeed after", expiration_time, "seconds and its",\
                          "state in etcd is deleted.\n"


# class CcpAciAsyncCreate inherits the threading.Thread class and
# configures ACI asynchronously in a different thread
class CcpAciAsyncCreate(threading.Thread):
    def __init__(self, ccp_aci_server):
        threading.Thread.__init__(self)
        self.ccp_aci_server = ccp_aci_server

    # this function runs in a different thread
    # (start() in threading.Thread class calls this function)
    def run(self):
        try:
            # delete expired and failed creations in progress if any
            self.ccp_aci_server._delete_expired_creations_in_progress()

            per_cluster_status = {
                "completed": False,
                "crt_file": "",
                "key_file": "",
                "aci_input_json": {},
                "aci_flavor": "",
                "output_aci_cni_yaml": [],
                "creation_start_time": time.time(),
                "key_name": self.ccp_aci_server.db_key
            }

            program_aci = False

            if self.ccp_aci_server.get_from_etcd()[0] is None:
                self.ccp_aci_server.delete_stale_key_in_etcd()
                self.ccp_aci_server.put_into_etcd(per_cluster_status)
                print "\nStored creation_status in etcd for new cluster", \
                    self.ccp_aci_server.db_key, "\n"
                program_aci = True

            if program_aci:
                print "Programming ACI for new cluster", \
                    self.ccp_aci_server.db_key, "\n"
                # update ACI input json
                self.ccp_aci_server.update_aci_input_json_for_cluster()
                self.ccp_aci_server.convert_input_json_to_yaml_file()
                if not self.ccp_aci_server.run_command_and_retry("create"):
                    raise Exception("Failed to program ACI for cluster " +
                                    self.ccp_aci_server.db_key)
                response = self.ccp_aci_server.get_response_list()
                self.ccp_aci_server.cleanup_files()
                # update creation_status for the successful cluster in etcd
                self.ccp_aci_server.update_creation_status_in_etcd(response)
                print "Done programming ACI for new cluster", \
                    self.ccp_aci_server.db_key, "\n"
            else:
                if json.loads(
                        self.ccp_aci_server.get_from_etcd()[0])["completed"]:
                    print "\nProgramming ACI for cluster", \
                        self.ccp_aci_server.db_key, "already done\n"
                else:
                    print "\nProgramming ACI for cluster", \
                        self.ccp_aci_server.db_key, "already in progress...\n"

        except Exception as e:
            # handle exception raised in thread
            print "\nERROR:", type(e), str(e), "in thread\n"
            logging.exception(e)
            try:
                self.ccp_aci_server.cleanup_files()
            except:
                pass
            # cleanup unfinished creation_status for failed cluster in etcd
            if self.ccp_aci_server.get_from_etcd()[0] is not None and \
               not json.loads(self.ccp_aci_server.get_from_etcd()[0])["completed"]:
                self.ccp_aci_server.delete_from_etcd()
            raise e


# class CcpAciAsyncDelete inherits the threading.Thread class and
# deletes ACI configs asynchronously in a different thread
class CcpAciAsyncDelete(threading.Thread):
    def __init__(self, ccp_aci_server):
        threading.Thread.__init__(self)
        self.ccp_aci_server = ccp_aci_server

    # this function runs in a different thread
    # (start() in threading.Thread class calls this function)
    def run(self):
        try:
            # also delete expired and failed creations in progress if any
            self.ccp_aci_server._delete_expired_creations_in_progress()

            if self.ccp_aci_server.get_from_etcd()[0] is None:
                print "\nState not found in etcd for cluster", self.ccp_aci_server.db_key, "\n"
                return

            print "Deleting ACI configs for cluster", \
                self.ccp_aci_server.db_key, "\n"
            self.ccp_aci_server.convert_input_json_to_yaml_file()
            self.ccp_aci_server.get_aci_certs_from_etcd()
            if not self.ccp_aci_server.run_command_and_retry("delete"):
                raise Exception("Failed to delete ACI configs for cluster " +
                                self.ccp_aci_server.db_key)
            self.ccp_aci_server.cleanup_files()

            # delete creation_status for cluster in etcd
            self.ccp_aci_server.delete_from_etcd()
            self.ccp_aci_server.delete_stale_key_in_etcd()
            aci_allocator = allocator.Allocator(
                self.ccp_aci_server.etcd_client,
                self.ccp_aci_server.config_file)
            if aci_allocator.get(self.ccp_aci_server.
                                 http_request["ccp_cluster_name"]) != {}:
                # free state stored by server/allocator.py
                aci_allocator.free(
                    self.ccp_aci_server.http_request["ccp_cluster_name"])

            print "Deleted ACI configs for cluster", \
                self.ccp_aci_server.db_key, "\n"

        except Exception as e:
            # handle exception raised in thread
            print "\nERROR:", type(e), str(e), "in thread\n"
            logging.exception(e)
            try:
                self.ccp_aci_server.cleanup_files()
            except:
                pass
            raise e
