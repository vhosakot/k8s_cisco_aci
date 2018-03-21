
clean:
	rm -rf server/*.pyc
	rm -rf python_client/aci_cni_*.yaml

clean-aci-certs:
	rm -rf server/*.crt
	rm -rf server/*.key

install:
	-apt-get -y install \
		python-openssl=0.15.1-2build1 python-yaml=3.11-3build1 \
		python-requests=2.9.1-3 python-jinja2=2.8-1 python-pip
	apt-get -y --fix-broken install
	apt-get -y install \
		python-openssl=0.15.1-2build1 python-yaml=3.11-3build1 \
		python-requests=2.9.1-3 python-jinja2=2.8-1 python-pip
	apt-get -y autoremove
	pip install --upgrade pip
	pip install -r requirements.txt
	dpkg -i acc-provision/acc-provision_1.8.0-30_amd64.deb
	acc-provision -v

tests:
	@bash ./scripts/tests.sh

.PHONY: clean clean-aci-certs install tests
