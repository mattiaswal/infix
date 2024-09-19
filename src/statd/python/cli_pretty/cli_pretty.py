#!/usr/bin/env python3
import json
import argparse
import sys
import re


class Pad:
    iface = 16
    proto = 11
    state = 12
    data = 41


class PadMdb:
    bridge = 7
    vlan = 6
    group = 20
    ports = 45


class PadRoute:
    prefix = 30
    protocol = 10
    next_hop = 30
    pref = 8


class PadSoftware:
    name = 10
    date = 25
    hash = 64
    state = 10
    version = 23


class PadUsbPort:
    title = 30
    name = 20
    state = 10


class Decore():
    @staticmethod
    def decorate(sgr, txt, restore="0"):
        return f"\033[{sgr}m{txt}\033[{restore}m"

    @staticmethod
    def invert(txt):
        return Decore.decorate("7", txt)

    @staticmethod
    def red(txt):
        return Decore.decorate("31", txt, "39")

    @staticmethod
    def green(txt):
        return Decore.decorate("32", txt, "39")

    @staticmethod
    def yellow(txt):
        return Decore.decorate("33", txt, "39")

    @staticmethod
    def underline(txt):
        return Decore.decorate("4", txt, "24")


def get_json_data(default, indata, *args):
    data = indata
    for arg in args:
        if arg in data:
            data = data.get(arg)
        else:
            return default

    return data

def remove_yang_prefix(key):
    parts = key.split(":", 1)
    if len(parts) > 1:
        return parts[1]
    return key


class Route:
    def __init__(self, data, ip):
        self.data = data
        self.prefix = data.get(f'ietf-{ip}-unicast-routing:destination-prefix', '')
        self.protocol = data.get('source-protocol', '').split(':')[-1]
        self.pref = data.get('route-preference', '')
        self.next_hop = []
        next_hop_list = get_json_data(None, self.data, 'next-hop', 'next-hop-list')
        if next_hop_list:
            for nh in next_hop_list["next-hop"]:
                if nh.get(f"ietf-{ip}-unicast-routing:address"):
                    self.next_hop.append(nh[f"ietf-{ip}-unicast-routing:address"])
                elif nh.get("outgoing-interface"):
                    self.next_hop.append(nh["outgoing-interface"])
                else:
                    self.next_hop.append("unspecified")
        else:
            interface = get_json_data(None, self.data, 'next-hop', 'outgoing-interface')
            address = get_json_data(None, self.data, 'next-hop', f'ietf-{ip}-unicast-routing:next-hop-address')
            special = get_json_data(None, self.data, 'next-hop', 'special-next-hop')

            if address:
                self.next_hop.append(address)
            elif interface:
                self.next_hop.append(interface)
            elif special:
                self.next_hop.append(special)
            else:
                self.next_hop.append("unspecified")

    def get_distance_and_metric(self):
        if isinstance(self.pref, int):
            distance = self.pref
            metric = 0
        else:
            distance, metric = 0, 0

        return distance, metric

    def print(self):
        distance, metric = self.get_distance_and_metric()
        pref = f"{distance}/{metric}"
        row = f"{self.prefix:<{PadRoute.prefix}}"
        row += f"{self.next_hop[0]:<{PadRoute.next_hop}}"
        row += f"{pref:>{PadRoute.pref}}  "
        row += f"{self.protocol:<{PadRoute.protocol}}"
        print(row)
        for nh in self.next_hop[1:]:
            row = f"{'':<{PadRoute.prefix}}"
            row += f"{nh:<{PadRoute.next_hop}}"
            print(row)


class Software:
    """Software bundle class """
    def __init__(self, data):
        self.data = data
        self.name = data.get('bootname', '')
        self.size = data.get('size', '')
        self.type = data.get('class', '')
        self.hash = data.get('sha256', '')
        self.state = data.get('state', '')
        self.version = get_json_data('', self.data, 'bundle', 'version')
        self.date = get_json_data('', self.data, 'installed', 'datetime')

    def is_rootfs(self):
        """True if bundle type is 'rootfs'"""
        return self.type == "rootfs"

    def print(self):
        """Brief information about one bundle"""
        row  = f"{self.name:<{PadSoftware.name}}"
        row += f"{self.state:<{PadSoftware.state}}"
        row += f"{self.version:<{PadSoftware.version}}"
        row += f"{self.date:<{PadSoftware.date}}"
        print(row)

    def detail(self):
        """Detailed information about one bundle"""
        print(f"Name      : {self.name}")
        print(f"State     : {self.state}")
        print(f"Version   : {self.version}")
        print(f"Size      : {self.size}")
        print(f"SHA-256   : {self.hash}")
        print(f"Installed : {self.date}")

class USBport:
    def __init__(self, data):
        self.data = data
        self.name = data.get('name', '')
        self.state = get_json_data('', self.data, 'state', 'admin-state')

    def print(self):
        #print(self.name)
        row = f"{self.name:<{PadUsbPort.name}}"
        row += f"{self.state:<{PadUsbPort.state}}"
        print(row)

class Iface:
    def __init__(self, data):
        self.data = data
        self.name = data.get('name', '')
        self.type = data.get('type', '')
        self.index = data.get('if-index', '')
        self.oper_status = data.get('oper-status', '')
        self.autoneg = get_json_data('unknown', self.data, 'ieee802-ethernet-interface:ethernet',
                                          'auto-negotiation', 'enable')
        self.duplex = get_json_data('', self.data,'ieee802-ethernet-interface:ethernet','duplex')
        self.speed = get_json_data('', self.data, 'ieee802-ethernet-interface:ethernet', 'speed')
        self.phys_address = data.get('phys-address', '')

        self.br_mdb = get_json_data({}, self.data, 'infix-interfaces:bridge', 'multicast-filters')
        self.br_vlans = get_json_data({}, self.data, 'infix-interfaces:bridge', 'vlans', "vlan")
        self.bridge = get_json_data('', self.data, 'infix-interfaces:bridge-port', 'bridge')
        self.pvid = get_json_data('', self.data, 'infix-interfaces:bridge-port', 'pvid')
        self.stp_state = get_json_data('', self.data, 'infix-interfaces:bridge-port', 'stp-state')

        if data.get('statistics'):
            self.in_octets = data.get('statistics').get('in-octets', '')
            self.out_octets = data.get('statistics').get('out-octets', '')
        else:
            self.in_octets = ''
            self.out_octets = ''

        if self.data.get('ietf-ip:ipv4'):
            self.mtu = self.data.get('ietf-ip:ipv4').get('mtu', '')
            self.ipv4_addr = self.data.get('ietf-ip:ipv4').get('address', '')
        else:
            self.mtu = ''
            self.ipv4_addr = []

        if self.data.get('ietf-ip:ipv6'):
            self.ipv6_addr = self.data.get('ietf-ip:ipv6').get('address', '')
        else:
            self.ipv6_addr = []


        if self.data.get('infix-interfaces:vlan'):
            self.lower_if = self.data.get('infix-interfaces:vlan', None).get('lower-layer-if',None)
        else:
            self.lower_if = ''

    def is_vlan(self):
        return self.type == "infix-if-type:vlan"

    def is_bridge(self):
        return self.type == "infix-if-type:bridge"

    def is_veth(self):
        return self.data['type'] == "infix-if-type:veth"

    def oper(self, detail=False):
        """Remap in brief overview to fit column widths."""
        if not detail and self.oper_status == "lower-layer-down":
            return "lower-down"
        return self.oper_status

    def pr_name(self, pipe=""):
        print(f"{pipe}{self.name:<{Pad.iface - len(pipe)}}", end="")

    def pr_proto_ipv4(self, pipe=''):
        for addr in self.ipv4_addr:
            origin = f"({addr['origin']})" if addr.get('origin') else ""

            row =  f"{pipe:<{Pad.iface}}"
            row += f"{'ipv4':<{Pad.proto}}"
            row += f"{'':<{Pad.state}}{addr['ip']}/{addr['prefix-length']} {origin}"
            print(row)

    def pr_proto_ipv6(self, pipe=''):
        for addr in self.ipv6_addr:
            origin = f"({addr['origin']})" if addr.get('origin') else ""

            row =  f"{pipe:<{Pad.iface}}"
            row += f"{'ipv6':<{Pad.proto}}"
            row += f"{'':<{Pad.state}}{addr['ip']}/{addr['prefix-length']} {origin}"
            print(row)

    def pr_proto_eth(self, pipe=''):
        row = ""
        if len(pipe) > 0:
            row =  f"{pipe:<{Pad.iface}}"

        row += f"{'ethernet':<{Pad.proto}}"
        dec = Decore.green if self.oper() == "up" else Decore.red
        row += dec(f"{self.oper().upper():<{Pad.state}}")
        row += f"{self.phys_address:<{Pad.data}}"
        print(row)

    def pr_proto_br(self, br_vlans):
        data_str = ""

        row = f"{'bridge':<{Pad.proto}}"

        if self.oper() == "up":
            dec = Decore.green if self.stp_state == "forwarding" else Decore.yellow
            row += dec(f"{self.stp_state.upper():<{Pad.state}}")
        else:
            row += Decore.red(f"{self.oper().upper():<{Pad.state}}")

        for vlan in br_vlans:
            if 'tagged' in vlan:
                for tagged in vlan['tagged']:
                    if tagged == self.name:
                        if data_str:
                            data_str += f",{vlan['vid']}t"
                        else:
                            data_str += f"vlan:{vlan['vid']}t"
            if 'untagged' in vlan:
                for untagged in vlan['untagged']:
                    if untagged == self.name:
                        if data_str:
                            data_str += f",{vlan['vid']}u"
                        else:
                            data_str += f"vlan:{vlan['vid']}u"
        if self.pvid:
            data_str += f" pvid:{self.pvid}"

        if data_str:
            row += f"{data_str:<{Pad.data}}"

        print(row)

    def pr_bridge(self, _ifaces):
        self.pr_name(pipe="")
        self.pr_proto_br(self.br_vlans)

        lowers = []
        for _iface in [Iface(data) for data in _ifaces]:
            if _iface.bridge and _iface.bridge == self.name:
                lowers.append(_iface)

        if lowers:
            self.pr_proto_eth(pipe='│')
            self.pr_proto_ipv4(pipe='│')
            self.pr_proto_ipv6(pipe='│')
        else:
            self.pr_proto_eth(pipe=' ')
            self.pr_proto_ipv4()
            self.pr_proto_ipv6()

        for i, lower in enumerate(lowers):
            pipe = '└ ' if (i == len(lowers) -1)  else '├ '
            lower.pr_name(pipe)
            lower.pr_proto_br(self.br_vlans)

    def pr_veth(self, _ifaces):
        self.pr_name(pipe="")
        self.pr_proto_eth()

        if self.lower_if:
            row = f"{'':<{Pad.iface}}"
            row += f"{'veth':<{Pad.proto}}"
            row += f"{'':<{Pad.state}}"
            row += f"peer:{self.lower_if}"
            print(row)

        self.pr_proto_ipv4()
        self.pr_proto_ipv6()

    def pr_vlan(self, _ifaces):
        self.pr_name(pipe="")
        self.pr_proto_eth()

        if self.lower_if:
            self.pr_proto_ipv4(pipe='│')
            self.pr_proto_ipv6(pipe='│')
        else:
            self.pr_proto_ipv4()
            self.pr_proto_ipv6()
            return

        parent = find_iface(_ifaces, self.lower_if)
        if not parent:
            print(f"Error, didn't find parent interface for vlan {self.name}")
            sys.exit(1)
        parent.pr_name(pipe='└ ')
        parent.pr_proto_eth()

    def pr_iface(self):
        print(f"{'name':<{20}}: {self.name}")
        print(f"{'index':<{20}}: {self.index}")
        if self.mtu:
            print(f"{'mtu':<{20}}: {self.mtu}")
        if self.oper():
            print(f"{'operational status':<{20}}: {self.oper(detail=True)}")

        if self.lower_if:
            print(f"{'lower-layer-if':<{20}}: {self.lower_if}")

        if self.autoneg != 'unknown':
            val = "on" if self.autoneg else "off"
            print(f"{'auto-negotiation':<{20}}: {val}")

        if self.duplex:
            print(f"{'duplex':<{20}}: {self.duplex}")

        if self.speed:
            mbs = float(self.speed) * 1000
            print(f"{'speed':<{20}}: {int(mbs)}")

        if self.phys_address:
            print(f"{'physical address':<{20}}: {self.phys_address}")

        if self.ipv4_addr:
            first = True
            for addr in self.ipv4_addr:
                origin = f"({addr['origin']})" if addr.get('origin') else ""
                key = 'ipv4 addresses' if first else ''
                colon = ':' if first else ' '
                row = f"{key:<{20}}{colon} "
                row += f"{addr['ip']}/{addr['prefix-length']} {origin}"
                print(row)
                first = False
        else:
                print(f"{'ipv4 addresses':<{20}}:")

        if self.ipv6_addr:
            first = True
            for addr in self.ipv6_addr:
                origin = f"({addr['origin']})" if addr.get('origin') else ""
                key = 'ipv6 addresses' if first else ''
                colon = ':' if first else ' '
                row = f"{key:<{20}}{colon} "
                row += f"{addr['ip']}/{addr['prefix-length']} {origin}"
                print(row)
                first = False
        else:
                print(f"{'ipv6 addresses':<{20}}:")

        if self.in_octets and self.out_octets:
            print(f"{'in-octets':<{20}}: {self.in_octets}")
            print(f"{'out-octets':<{20}}: {self.out_octets}")

        frame = get_json_data([], self.data,'ieee802-ethernet-interface:ethernet',
                              'statistics', 'frame')
        if frame:
            print("")
            for key, val in frame.items():
                key = remove_yang_prefix(key)
                print(f"eth-{key:<{25}}: {val}")

    def pr_mdb(self, bridge):
        for group in self.br_mdb.get("multicast-filter", {}):
            row = f"{bridge:<{PadMdb.bridge}}"
            row += f"{'':<{PadMdb.vlan}}"
            row += f"{group['group']:<{PadMdb.group}}"
            if (group.get("ports")):
                ports = ", ".join(port_dict["port"] for port_dict in group["ports"])
            else:
                ports = ""
            row += f"{ports}"
            print(row)

    def pr_vlans_mdb(self, bridge):
        for vlan in self.br_vlans:
            filters=vlan.get("multicast-filters", {})
            for group in filters.get("multicast-filter", []):
                row = f"{bridge:<{PadMdb.bridge}}"
                row += f"{vlan['vid']:<{PadMdb.vlan}}"
                row += f"{group['group']:<{PadMdb.group}}"
                if (group.get("ports")):
                   ports = ", ".join(port_dict["port"] for port_dict in group["ports"])
                else:
                    ports = ""
                row += f"{ports}"
                print(row)


def find_iface(_ifaces, name):
    for _iface in [Iface(data) for data in _ifaces]:
        if _iface.name == name:
            return _iface

    return False


def version_sort(iface):
    return [int(x) if x.isdigit() else x for x in re.split(r'(\d+)',
                                                           iface['name'])]


def print_interface(iface):
    iface.pr_name()
    iface.pr_proto_eth()
    iface.pr_proto_ipv4()
    iface.pr_proto_ipv6()


def pr_interface_list(json):
    hdr = (f"{'INTERFACE':<{Pad.iface}}"
           f"{'PROTOCOL':<{Pad.proto}}"
           f"{'STATE':<{Pad.state}}"
           f"{'DATA':<{Pad.data}}")

    print(Decore.invert(hdr))

    ifaces = sorted(json["ietf-interfaces:interfaces"]["interface"],
                    key=version_sort)
    iface = find_iface(ifaces, "lo")
    if iface:
        print_interface(iface)

    for iface in [Iface(data) for data in ifaces]:
        if iface.name == "lo":
            continue

        if iface.is_bridge():
            iface.pr_bridge(ifaces)
            continue

        if iface.is_veth():
            iface.pr_veth(ifaces)
            continue

        if iface.is_vlan():
            iface.pr_vlan(ifaces)
            continue

        # These interfaces are printed by there parent, such as bridge
        if iface.lower_if:
            continue
        if iface.bridge:
            continue
        print_interface(iface)


def show_interfaces(json, name):
    if name:
        if not json.get("ietf-interfaces:interfaces"):
            print(f"No interface data found for \"{name}\"")
            sys.exit(1)
        iface = find_iface(json["ietf-interfaces:interfaces"]["interface"], name)
        if not iface:
            print(f"Interface \"{name}\" not found")
            sys.exit(1)
        else:
            iface.pr_iface()
    else:
        if not json.get("ietf-interfaces:interfaces"):
            print("Error, top level \"ietf-interfaces:interfaces\" missing")
            sys.exit(1)
        pr_interface_list(json)


def show_bridge_mdb(json):
    header_printed = False
    if not json.get("ietf-interfaces:interfaces"):
        print("Error, top level \"ietf-interfaces:interface\" missing")
        sys.exit(1)

    ifaces = sorted(json["ietf-interfaces:interfaces"]["interface"],
                    key=version_sort)
    for iface in [Iface(data) for data in ifaces]:
        if iface.type != "infix-if-type:bridge":
            continue
        if not header_printed:
            hdr = (f"{'BRIDGE':<{PadMdb.bridge}}"
                   f"{'VID':<{PadMdb.vlan}}"
                   f"{'GROUP':<{PadMdb.group}}"
                   f"{'PORTS':<{PadMdb.ports}}")
            print(Decore.invert(hdr))
            header_printed = True
        iface.pr_mdb(iface.name)
        iface.pr_vlans_mdb(iface.name)


def show_routing_table(json, ip):
    if not json.get("ietf-routing:routing"):
        print("Error, top level \"ietf-routing:routing\" missing")
        sys.exit(1)

    hdr = (f"{'PREFIX':<{PadRoute.prefix}}"
           f"{'NEXT-HOP':<{PadRoute.next_hop}}"
           f"{'PREF':>{PadRoute.pref}}  "
           f"{'PROTOCOL':<{PadRoute.protocol}}")

    print(Decore.invert(hdr))
    for rib in get_json_data({}, json, 'ietf-routing:routing', 'ribs', 'rib'):
        if rib["name"] != ip:
            continue

        routes = get_json_data(None, rib, "routes", "route")
        if routes:
            for r in routes:
                route = Route(r, ip)
                route.print()


def find_slot(_slots, name):
    for _slot in [Software(data) for data in _slots]:
        if _slot.name == name:
            return _slot

    return False


def show_software(json, name):
    if not json.get("ietf-system:system-state", "infix-system:software"):
        print("Error, cannot find infix-system:software")
        sys.exit(1)

    slots = get_json_data({}, json, 'ietf-system:system-state', 'infix-system:software', 'slot')
    if name:
        slot = find_slot(slots, name)
        if slot:
            slot.detail()
    else:
        hdr = (f"{'NAME':<{PadSoftware.name}}"
               f"{'STATE':<{PadSoftware.state}}"
               f"{'VERSION':<{PadSoftware.version}}"
               f"{'DATE':<{PadSoftware.date}}")
        print(Decore.invert(hdr))
        for _s in slots:
            slot = Software(_s)
            if slot.is_rootfs():
                slot.print()

def show_hardware(json):
    if not json.get("ietf-hardware:hardware"):
       print(f"Error, top level \"ietf-hardware:component\" missing")
       sys.exit(1)

    hdr = (f"{'USB PORTS':<{PadUsbPort.title}}")
    print(Decore.invert(hdr))
    hdr =  (f"{'NAME':<{PadUsbPort.name}}"
            f"{'STATE':<{PadUsbPort.state}}")
    print(Decore.invert(hdr))

    components = get_json_data({}, json, "ietf-hardware:hardware", "component")

    for component in components:
        if component.get("class") == "infix-hardware:usb":
            port = USBport(component)
            port.print()

def main():
    try:
        json_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("Error, invalid JSON input")
        sys.exit(1)
    except Exception as e:
        print("Error, unexpected error parsing JSON")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="JSON CLI Pretty Printer")
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    parser_show_routing_table = subparsers.add_parser('show-routing-table', help='Show the routing table')
    parser_show_routing_table.add_argument('-i', '--ip', required=True, help='IPv4 or IPv6 address')

    parser_show_interfaces = subparsers.add_parser('show-interfaces', help='Show interfaces')
    parser_show_interfaces.add_argument('-n', '--name', help='Interface name')

    parser_show_bridge_mdb = subparsers.add_parser('show-bridge-mdb', help='Show bridge MDB')

    parser_show_software = subparsers.add_parser('show-software', help='Show software versions')
    parser_show_software.add_argument('-n', '--name', help='Slotname')

    parser_show_routing_table = subparsers.add_parser('show-hardware', help='Show USB ports')

    args = parser.parse_args()

    if args.command == "show-interfaces":
        show_interfaces(json_data, args.name)
    elif args.command == "show-routing-table":
        show_routing_table(json_data, args.ip)
    elif args.command == "show-software":
        show_software(json_data, args.name)
    elif args.command == "show-bridge-mdb":
        show_bridge_mdb(json_data)
    elif args.command == "show-hardware":
        show_hardware(json_data)
    else:
        print(f"Error, unknown command {args.command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
