import etcd3
import os
import pytest

from allocator import *

etcd_address = os.environ["ETCD_CONTAINER_IP"]
etcd = etcd3.client(host=etcd_address)

# ===== HELPER FUNCTIONS ============================================================================

def dump_etcd():
    print(etcd.get(Allocator.DB_KEY)[0])

def wipe_etcd():
    etcd.delete(Allocator.DB_KEY)

def setup_function(function):
    print("running test function: %s" % function.__name__)


def teardown_function(function):
    print("before wipe:")
    dump_etcd()
    wipe_etcd()

    print("after wipe:")
    dump_etcd()
    print("")

def stock_allocator():
    return Allocator(etcd)

# ===== TESTS =======================================================================================

# ----- helper functions ----------------------------------------------------------------------------

def test_increment_ip():
    assert increment_ip("10.0.0.1", 1) == "10.0.0.2"
    assert increment_ip("10.0.0.255", 1) == "10.0.1.0"
    assert increment_ip("10.0.0.0", 2**16) == "10.1.0.0"

    with pytest.raises(ValueError, message="increment value must be >= 0"):
        assert increment_ip("10.0.0.0", 0)

    with pytest.raises(InvalidIPError, message="IP 255.255.255.255 can't be incremented by 1"):
        assert increment_ip("255.255.255.255", 1)

    # TODO: test non-sensical input

def test_generate_next_subnet():
    assert generate_next_subnet("10.0.0.0/24") == "10.1.0.0/24"
    assert generate_next_subnet("10.0.0.0/16", "/16") == "10.1.0.0/16"

    with pytest.raises(InvalidIPError, message="IP 255.255.0.0 can't be incremented by " + str(2**16)):
        assert generate_next_subnet("255.255.0.0/24")

    # TODO: test non-sensical input

def test_start_and_end_addresses_for_mcast_range():
    assert start_and_end_addresses_for_mcast_range("10.0.0.0/16") == ("10.0.1.1", "10.0.255.255")

# ----- Allocator class -----------------------------------------------------------------------------

def test_getting():
    a = stock_allocator()
    assert a.get("foo") == {}

    a.reserve("foo")
    assert a.get("foo") != {}

def test_validating_inputs():
    # vlan_min too low
    with pytest.raises(ValueError, message="vlan_min must be >= 1 (got 0)"):
        Allocator(etcd, vlan_min=0)

    # vlan_max too high
    with pytest.raises(ValueError, message="vlan_max must be <= 4094 (got 4095)"):
        Allocator(etcd, vlan_max=4095)

    # too few vlan ids
    with pytest.raises(ValueError, message="TODO"):
        Allocator(etcd, vlan_min=2000, vlan_max=2000)

def test_reservations():
    a = stock_allocator()
    foo = a.reserve("foo")

    assert foo[Allocator.KUBEAPI_VLAN_KEY] == Allocator.DEFAULT_VLAN_MIN
    assert foo[Allocator.SERVICE_VLAN_KEY] == Allocator.DEFAULT_VLAN_MIN + 1
    assert foo[Allocator.SERVICE_SUBNET_KEY] == Allocator.DEFAULT_SERVICE_SUBNET

    start_address, end_address = start_and_end_addresses_for_mcast_range(Allocator.DEFAULT_MULTICAST_RANGE)

    assert foo[Allocator.MULTICAST_RANGE_START_KEY] == start_address
    assert foo[Allocator.MULTICAST_RANGE_END_KEY] == end_address

    bar = a.reserve("bar")

    assert bar[Allocator.KUBEAPI_VLAN_KEY] == Allocator.DEFAULT_VLAN_MIN + 2
    assert bar[Allocator.SERVICE_VLAN_KEY] == Allocator.DEFAULT_VLAN_MIN + 3

    svc_subnet = generate_next_subnet(Allocator.DEFAULT_SERVICE_SUBNET)
    assert bar[Allocator.SERVICE_SUBNET_KEY] == svc_subnet

    mcast_range = generate_next_subnet(Allocator.DEFAULT_MULTICAST_RANGE, "/16")
    start_address, end_address = start_and_end_addresses_for_mcast_range(mcast_range)

    assert bar[Allocator.MULTICAST_RANGE_START_KEY] == start_address
    assert bar[Allocator.MULTICAST_RANGE_END_KEY] == end_address

    a.free("bar")
    a.free("foo")

def test_allow_tenant_name_characters():
    a = stock_allocator()

    with pytest.raises(InvalidNameError):
        a.reserve("")

    with pytest.raises(InvalidNameError):
        a.reserve("no spaces allowed")

    a.reserve("legal_name")
    a.reserve("also-legal")

def test_reusing_tenant_name():
    a = stock_allocator()
    a.reserve("foo")

    with pytest.raises(TenantAlreadyExistsError):
        a.reserve("foo")

def test_freeing_tenant():
    a = stock_allocator()

    a.reserve("foo")
    a.free("foo")

    with pytest.raises(TenantDoesNotExistError):
        a.free("foo")

def test_freeing_nonexistent_tenant():
    a = stock_allocator()

    with pytest.raises(TenantDoesNotExistError):
        a.free("foo")

def test_allocating_mad_vlans():
    a = Allocator(etcd, vlan_min=1000, vlan_max=1001)

    with pytest.raises(InsufficientVLANsAvailableError):
        for i in range(0, 2):
            # each reservation consumes 2 vlans so the second one should fail
            a.reserve("foo" + str(i))

def test_allocating_too_many_service_subnets():
    a = Allocator(etcd, service_subnet="255.254.0.0/24")

    with pytest.raises(NoServiceSubnetsAvailableError):
        for i in range(0, 3):
            a.reserve("foo" + str(i))

def test_allocating_too_many_multicast_ranges():
    a = Allocator(etcd, multicast_range="255.254.0.0/16")

    with pytest.raises(NoMulticastRangesAvailableError):
        for i in range(0, 3):
            a.reserve("foo" + str(i))
