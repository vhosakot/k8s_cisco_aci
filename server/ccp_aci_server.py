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

################################################################
#                                                              #
# REST server to create and delete configs on ACI fabric using #
# acc-provision and per-tenant input json for each CCP tenant  #
# cluster                                                      #
#                                                              #
# Run "./ccp_aci_server.py -h" to see usage                    #
#                                                              #
################################################################

import argparse
import etcd3
import json
import logging
import sys
from datetime import datetime
from flask import Flask, jsonify
from flask import request
from server import *

app = Flask(__name__)
parser = argparse.ArgumentParser()
parser.add_argument(
    '--ip',
    help='IP address to listen on. Default is 0.0.0.0',
    default='0.0.0.0')
parser.add_argument(
    '--port',
    help='Port to listen on. Default is 46802',
    type=int,
    default=46802)
parser.add_argument(
    '--config_file',
    help='Path to config file. Default is aci.conf',
    default='aci.conf')
parser.add_argument(
    'etcd_ip_port',
    help="etcd server's IP address or DNS name and port in the " \
         "format <etcd's IP or DNS name>:<etcd port>")
args = parser.parse_args()

# validate etcd_ip_port
if ':' not in args.etcd_ip_port or \
    not args.etcd_ip_port.split(':')[1].isdigit():
    print "\nERROR: Invalid etcd_ip_port. etcd_ip_port's format is \
           \n<IP address or DNS name of etcd server>:<port of etcd server>\n"

    sys.exit(1)

# validate if etcd server is up
etcd_client = etcd3.client(
    host=args.etcd_ip_port.split(':')[0], port=args.etcd_ip_port.split(':')[1])
try:
    etcd_client.get('foo')
except Exception as e:
    print type(e), str(e), "\n"
    logging.exception(e)
    print "\nERROR: etcd server not up at", args.etcd_ip_port, "\n"
    import os
    os._exit(1)

# validate if "acc-provision" command works as CCP ACI service needs
# the "acc-provision" command to work
result = CcpAciServer.run_command("acc-provision -v")
if result is None:
    print "\nERROR: The command \"acc-provision -v\" did not work. " \
           "CCP ACI service needs the \"acc-provision\" command to work.\n" \
           "Install acc-provision and make sure that "\
           "\"acc-provision -v\" works before starting this service.\n"
    sys.exit(1)

# at this point, it is safe to start the server as both etcd and acc-provision
# are working


@app.before_request
def log_request_info():
    try:
        req = json.loads(request.get_data())
        # don't print ACI username and password in logs
        req["aci_username"] = ""
        req["aci_password"] = ""
        app.logger.debug(
            datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f') + ' Body: %s',
            json.dumps(req))
    except Exception:
        # no need print debugs for invalid non-json payload
        pass


# function to validate http request
def validate_http_request(request, create=False):
    if request is None:
        return "Bad request, payload is empty"

    elif not CcpAciServer.validate_http_payload(request, create):
        print "ERROR: Bad request: ", request
        return "Bad request"

    elif request["ccp_cluster_name"] == '' or \
       ' ' in request["ccp_cluster_name"]:
        print "ERROR: Bad request: ", request
        return "ccp_cluster_name must be one " \
               "or more characters without spaces"
    else:
        return ''


# HTTP POST to create configs on ACI fabric asynchronously using acc-provision
# and per-tenant input json for each CCP tenant cluster
@app.route('/api/v1/acc_provision_create', methods=['POST'])
def acc_provision_create():
    ccp_aci_server = None

    try:
        err = validate_http_request(request.json, create=True)
        if err != '':
            return jsonify({"error": err}), 400

        global etcd_client

        ccp_aci_server = CcpAciServer(request.json, etcd_client,
                                      args.config_file)

        # block duplicate cluster name in etcd
        if ccp_aci_server.cluster_name_is_duplicate():
            return jsonify({
                "error": "Duplicate cluster name " + request.json["ccp_cluster_name"] + \
                         ". Use a different cluster name."
            }), 400

        async_task = CcpAciAsyncCreate(ccp_aci_server)

        # configure ACI asynchronously in a different thread
        # (async_task.start() calls run() in CcpAciAsyncCreate class in a different thread)
        async_task.start()

        # send json response back
        return jsonify({
            "response": "Request accepted to create ACI configs. "\
                        "Use http endpoint /api/v1/acc_provision_status "\
                        "to get the ACI CNI for the cluster."
        }), 202

    except Exception as e:
        print "\nERROR: acc_provision_create failed\n"
        print type(e), str(e), "\n"
        logging.exception(e)
        if ccp_aci_server is not None:
            ccp_aci_server.cleanup_files()
        return jsonify({"error": "Failed to configure ACI"}), 500


# HTTP GET that returns the per-cluster ACI CNI as json if it exists
# in etcd
#
# after posting to /api/v1/acc_provision_create, if this function
# always returns 404 as the http status code, then it means the creation
# failed, and client must post to /api/v1/acc_provision_create again to
# re-try creating the ACI configs
#
# after deleting using /api/v1/acc_provision_delete, if this function
# returns 404 as the http status code, then it means the deletion succeeded
#
@app.route('/api/v1/acc_provision_status', methods=['GET'])
def acc_provision_status():
    try:
        err = validate_http_request(request.json)
        if err != '':
            return jsonify({"error": err}), 400

        global etcd_client

        ccp_aci_server = CcpAciServer(request.json, etcd_client,
                                      args.config_file)

        allocator_state, aci_cni = ccp_aci_server.get_aci_cni_for_cluster_from_etcd(
        )

        if not aci_cni:
            msg =  "ERROR: ACI CNI not found for cluster. "\
                   "Use http endpoint /api/v1/acc_provision_create to "\
                   "create (POST) configs on ACI first, and then use "\
                   "this endpoint to get the ACI CNI for the cluster. "\
                   "If http endpoint /api/v1/acc_provision_delete was "\
                   "used to delete the ACI configs, then this message "\
                   "means the deletion was successful."
            return jsonify({"error": msg}), 404

        elif 'in progress' in aci_cni:
            return jsonify({"message": aci_cni}), 200

        else:
            # send allocator state and ACI CNI as json in response
            return jsonify({
                "ccp_cluster_name":
                request.json["ccp_cluster_name"],
                "allocator_state":
                allocator_state,
                "aci_cni_response":
                aci_cni
            }), 200

    except Exception as e:
        print "\nERROR: acc_provision_status failed\n"
        print type(e), str(e), "\n"
        logging.exception(e)
        return jsonify({"error": "Failed to get ACI CNI for cluster"}), 500


# HTTP DELETE to delete configs on ACI fabric asynchronously using acc-provision
# and per-tenant input json for each CCP tenant cluster
@app.route('/api/v1/acc_provision_delete', methods=['DELETE'])
def acc_provision_delete():
    ccp_aci_server = None

    try:
        err = validate_http_request(request.json)
        if err != '':
            return jsonify({"error": err}), 400

        global etcd_client

        ccp_aci_server = CcpAciServer(request.json, etcd_client,
                                      args.config_file)

        async_task = CcpAciAsyncDelete(ccp_aci_server)

        # delete ACI configs asynchronously in a different thread
        # (async_task.start() calls run() in CcpAciAsyncDelete class in a different thread)
        async_task.start()

        # send json response back
        return jsonify({
            "response": "Request accepted to delete ACI configs. "\
                        "Use http endpoint /api/v1/acc_provision_status "\
                        "to get the status."
        }), 202

    except Exception as e:
        print "\nERROR: acc_provision_delete failed\n"
        print type(e), str(e), "\n"
        logging.exception(e)
        if ccp_aci_server is not None:
            ccp_aci_server.cleanup_files()
        return jsonify({"error": "Failed to delete ACI configs"}), 500


# HTTP GET that checks if etcd is healthy and returns the supported APIs
# and version of acc-provision tool
#
# this url can be used for httpGet of kubernetes' livenessProbe
# to probe the health of this service in k8s
#
@app.route('/', methods=['GET'])
def acc_provision_get():
    try:
        e = etcd3.client(
            host=args.etcd_ip_port.split(':')[0],
            port=args.etcd_ip_port.split(':')[1])
        e.get('foo')
        result = CcpAciServer.run_command("acc-provision -v")
        if result is None:
            raise Exception("Failed to run the command \"acc-provision -v\"")
        return jsonify({
            'acc-provision': {
                'version':
                result.replace('\n', ''),
                'url': [
                    'HTTP POST   /api/v1/acc_provision_create',
                    'HTTP DELETE /api/v1/acc_provision_delete',
                    'HTTP GET    /api/v1/acc_provision_status', 'HTTP GET    /'
                ],
                'git_sha1':
                CcpAciServer.get_version().replace('\n', '')
            }
        }), 200
    except etcd3.exceptions.ConnectionFailedError as e:
        err = "ERROR: etcd server not up at " + args.etcd_ip_port
        print "\n", err, "\n"
        print type(e), str(e), "\n"
        logging.exception(e)
        return jsonify({"error": err}), 500
    except Exception as e:
        print "\nERROR: acc_provision_get failed\n"
        print type(e), str(e), "\n"
        logging.exception(e)
        return jsonify({"error": "Failed to run acc-provision tool"}), 500


if __name__ == '__main__':
    app.run(host=args.ip, port=args.port, debug=True, threaded=True)
