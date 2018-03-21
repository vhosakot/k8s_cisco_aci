# ubuntu xenial 16.04 container to containerize CCP ACI service
FROM ubuntu:16.04
MAINTAINER CCP team, Cisco Systems

# install required dependencies
RUN apt-get -y update && apt-get -y upgrade && \
    apt-get -y install --no-install-recommends \
        python2.7 python-setuptools=20.7.0-1 python-minimal=2.7.12-1~16.04 \
        python-openssl=0.15.1-2build1 python-yaml=3.11-3build1 \
        python-requests=2.9.1-3 python-jinja2=2.8-1 python-pip && \
    pip install --upgrade pip && \
    pip install wheel==0.29.0 Flask==0.12.2 PyYAML==3.12 \
        etcd3==0.7.0 iptools==0.6.1 netaddr==0.7.19 pyOpenSSL==16.2.0 && \
    # remove unwanted stuff in the container
    pip uninstall -y pip && \
    apt-get -y remove --purge python-pip && \
    apt-get -y clean all && apt-get -y autoclean && \
    apt-get -y autoremove && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /root/.cache/pip

# copy ACI acc-provision tool and source code into the container
COPY acc-provision/acc-provision_1.8.0-30_amd64.deb acc-provision_1.8.0-30_amd64.deb
COPY server/ccp_aci_server.py /ccp_aci_server.py
COPY server/server.py /server.py
COPY server/allocator.py /allocator.py
COPY ccp_aci_service_version /ccp_aci_service_version

# install acc-provision tool
RUN dpkg -i acc-provision_1.8.0-30_amd64.deb && \
    rm -rf acc-provision_1.8.0-30_amd64.deb && \
    mkdir /ccp-aci-certs && chmod 777 /ccp_aci_server.py

EXPOSE 46802

# start CCP ACI REST service
WORKDIR /ccp-aci-certs
ENV PYTHONUNBUFFERED=0
ENV PYTHONIOENCODING=UTF-8
CMD ["/ccp_aci_server.py", "0.0.0.0:2379"]
