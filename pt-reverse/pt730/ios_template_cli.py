#!/usr/bin/env python3
"""Render high-level IOS JSON templates to command sequences."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("IOS template must be a JSON object")
    return data


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_value_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    return value if isinstance(value, list) else [value]


def as_object_list(value: Any) -> list[dict[str, Any]]:
    if value in (None, "", []):
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        if not all(isinstance(item, dict) for item in value):
            raise ValueError("entries must be objects")
        return value
    raise ValueError("entries must be objects")


def require(value: Any, message: str) -> Any:
    if value in (None, ""):
        raise ValueError(message)
    return value


def vlan_list(value: Any) -> str:
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def space_list(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value)


def render_switchport_commands(spec: dict[str, Any]) -> list[str]:
    commands: list[str] = []
    mode = str(spec.get("mode", "")).lower()
    if mode in ("routed", "l3") or spec.get("switchport") is False:
        commands.append(" no switchport")
    if mode == "trunk":
        commands.extend([" switchport mode trunk", f" switchport trunk allowed vlan {vlan_list(spec.get('allowed_vlans', 'all'))}"])
    elif mode == "access":
        commands.extend([" switchport mode access", f" switchport access vlan {require(spec.get('vlan'), 'access interface vlan is required')}"])
    if spec.get("ip"):
        commands.append(f" ip address {spec['ip']} {require(spec.get('mask'), 'interface mask is required')}")
    return commands


def render_standby_commands(value: Any) -> list[str]:
    commands: list[str] = []
    for entry in as_object_list(value):
        group = entry.get("group", entry.get("id", 1))
        if entry.get("version"):
            commands.append(f" standby version {entry['version']}")
        virtual_ip = entry.get("ip", entry.get("virtual_ip", entry.get("address")))
        if virtual_ip:
            commands.append(f" standby {group} ip {virtual_ip}")
        if entry.get("priority") not in (None, ""):
            commands.append(f" standby {group} priority {entry['priority']}")
        if entry.get("preempt"):
            commands.append(f" standby {group} preempt")
        if entry.get("name"):
            commands.append(f" standby {group} name {entry['name']}")
        if entry.get("authentication"):
            commands.append(f" standby {group} authentication {entry['authentication']}")
        timers = entry.get("timers")
        if isinstance(timers, dict):
            commands.append(f" standby {group} timers {require(timers.get('hello'), 'hsrp timer hello is required')} {require(timers.get('hold'), 'hsrp timer hold is required')}")
        for track in as_value_list(entry.get("track")):
            if isinstance(track, dict):
                target = require(track.get("interface", track.get("object", track.get("name"))), "hsrp track target is required")
                line = f" standby {group} track {target}"
                if track.get("decrement") not in (None, ""):
                    line += f" {track['decrement']}"
                commands.append(line)
            elif track not in (None, ""):
                commands.append(f" standby {group} track {track}")
    return commands


def render_l3_interface_feature_commands(spec: dict[str, Any]) -> list[str]:
    commands: list[str] = []
    helper_values = spec.get("helper_addresses", spec.get("ip_helpers", spec.get("dhcp_relays")))
    for address in as_value_list(helper_values):
        commands.append(f" ip helper-address {address}")
    commands.extend(render_standby_commands(spec.get("hsrp", spec.get("standby"))))
    return commands


def render_dhcp_commands(value: Any) -> list[str]:
    commands: list[str] = []
    if not isinstance(value, dict):
        return commands
    excluded = value.get("excluded_addresses", value.get("excluded"))
    for entry in as_value_list(excluded):
        if isinstance(entry, dict):
            start = require(entry.get("start"), "dhcp excluded start is required")
            end = entry.get("end")
            commands.append(f"ip dhcp excluded-address {start}" + (f" {end}" if end else ""))
        else:
            commands.append(f"ip dhcp excluded-address {entry}")
    for pool in as_object_list(value.get("pools")):
        name = require(pool.get("name"), "dhcp pool name is required")
        commands.append(f"ip dhcp pool {name}")
        if pool.get("network"):
            commands.append(f" network {pool['network']} {require(pool.get('mask'), 'dhcp pool mask is required')}")
        if pool.get("default_router", pool.get("gateway")):
            commands.append(f" default-router {space_list(pool.get('default_router', pool.get('gateway')))}")
        if pool.get("dns_server", pool.get("dns")):
            commands.append(f" dns-server {space_list(pool.get('dns_server', pool.get('dns')))}")
        if pool.get("domain_name", pool.get("domain")):
            commands.append(f" domain-name {pool.get('domain_name', pool.get('domain'))}")
        if pool.get("lease"):
            commands.append(f" lease {space_list(pool['lease'])}")
        commands.append("exit")
    return commands


def render_ntp_commands(value: Any) -> list[str]:
    commands: list[str] = []
    if value in (None, "", []):
        return commands
    ntp = value if isinstance(value, dict) else {"servers": value}
    if not isinstance(ntp, dict):
        raise ValueError("ntp must be an object or server list")
    for key in as_object_list(ntp.get("authentication_keys")):
        commands.append(f"ntp authentication-key {require(key.get('id'), 'ntp key id is required')} md5 {require(key.get('md5', key.get('secret')), 'ntp key md5 is required')}")
    if ntp.get("authenticate"):
        commands.append("ntp authenticate")
    for trusted_key in as_value_list(ntp.get("trusted_keys")):
        commands.append(f"ntp trusted-key {trusted_key}")
    if ntp.get("source_interface", ntp.get("source")):
        commands.append(f"ntp source {ntp.get('source_interface', ntp.get('source'))}")
    for server in as_value_list(ntp.get("servers")):
        if isinstance(server, dict):
            address = require(server.get("address", server.get("host")), "ntp server address is required")
            parts = ["ntp server", str(address)]
            if server.get("version"):
                parts.extend(["version", str(server["version"])])
            if server.get("key"):
                parts.extend(["key", str(server["key"])])
            if server.get("source"):
                parts.extend(["source", str(server["source"])])
            if server.get("prefer"):
                parts.append("prefer")
            commands.append(" ".join(parts))
        else:
            commands.append(f"ntp server {server}")
    return commands


def render_logging_commands(value: Any) -> list[str]:
    commands: list[str] = []
    if value in (None, "", []):
        return commands
    logging = value if isinstance(value, dict) else {"hosts": value}
    if not isinstance(logging, dict):
        raise ValueError("logging must be an object or host list")
    if logging.get("timestamps_log"):
        commands.append("service timestamps log datetime msec")
    if logging.get("disable_console") or logging.get("no_console"):
        commands.append("no logging console")
    if logging.get("source_interface", logging.get("source")):
        commands.append(f"logging source-interface {logging.get('source_interface', logging.get('source'))}")
    if logging.get("trap"):
        commands.append(f"logging trap {logging['trap']}")
    for host in as_value_list(logging.get("hosts", logging.get("servers"))):
        if isinstance(host, dict):
            address = require(host.get("address", host.get("host")), "logging host address is required")
            line = f"logging host {address}"
            if host.get("vrf"):
                line += f" vrf {host['vrf']}"
            commands.append(line)
        else:
            commands.append(f"logging host {host}")
    return commands


def render_snmp_commands(value: Any) -> list[str]:
    commands: list[str] = []
    if not isinstance(value, dict):
        return commands
    for community in as_value_list(value.get("communities")):
        if isinstance(community, dict):
            name = require(community.get("name", community.get("community")), "snmp community name is required")
            mode = str(community.get("mode", community.get("access", "RO"))).upper()
            line = f"snmp-server community {name} {mode}"
            if community.get("acl"):
                line += f" {community['acl']}"
            commands.append(line)
        else:
            commands.append(f"snmp-server community {community} RO")
    if value.get("location"):
        commands.append(f"snmp-server location {value['location']}")
    if value.get("contact"):
        commands.append(f"snmp-server contact {value['contact']}")
    for host in as_object_list(value.get("hosts")):
        address = require(host.get("address", host.get("host")), "snmp host address is required")
        line = f"snmp-server host {address}"
        if host.get("version"):
            line += f" version {host['version']}"
        if host.get("community"):
            line += f" {host['community']}"
        commands.append(line)
    return commands


def schema_doc() -> dict[str, Any]:
    example = {
        "device": "R1",
        "hostname": "R1",
        "ip_routing": True,
        "vlans": [{"id": 10, "name": "SERVER"}],
        "interfaces": [
            {"name": "GigabitEthernet0/0", "ip": "10.0.0.1", "mask": "255.255.255.0", "acl_in": 10, "nat": "inside"},
            {"name": "GigabitEthernet0/1", "mode": "trunk", "allowed_vlans": [10, 20]},
            {"name": "GigabitEthernet0/2", "mode": "routed", "ip": "10.10.12.1", "mask": "255.255.255.252"},
            {"name": "Vlan10", "ip": "192.168.10.2", "mask": "255.255.255.0", "helper_addresses": ["172.16.1.10"], "hsrp": {"group": 10, "ip": "192.168.10.1", "priority": 110, "preempt": True}},
            {"name": "FastEthernet0/1", "mode": "access", "vlan": 10},
        ],
        "spanning_tree": {
            "mode": "rapid-pvst",
            "root_primary": [10, 20],
            "vlan_priorities": [{"vlan": 30, "priority": 4096}],
            "portfast_default": True,
            "bpduguard_default": True,
        },
        "etherchannels": [
            {
                "group": 1,
                "mode": "active",
                "interfaces": ["GigabitEthernet0/1", "GigabitEthernet0/2"],
                "port_channel": {"mode": "trunk", "allowed_vlans": [10, 20], "description": "UPLINK_BUNDLE"},
            }
        ],
        "rip": {"version": 2, "networks": ["10.0.0.0"], "no_auto_summary": True},
        "ospf": {
            "process_id": 1,
            "router_id": "10.255.0.1",
            "passive_interfaces": ["Vlan10"],
            "networks": [{"network": "10.0.0.0", "wildcard": "0.0.0.255", "area": 0}],
        },
        "static_routes": [{"destination": "0.0.0.0", "mask": "0.0.0.0", "next_hop": "10.0.0.254"}],
        "dhcp": {
            "excluded_addresses": [{"start": "192.168.10.1", "end": "192.168.10.20"}],
            "pools": [{"name": "VLAN10", "network": "192.168.10.0", "mask": "255.255.255.0", "default_router": "192.168.10.1", "dns_server": ["172.16.1.10"]}],
        },
        "ntp": {"servers": [{"address": "172.16.1.20", "prefer": True}], "source_interface": "Vlan10"},
        "logging": {"hosts": ["172.16.1.30"], "trap": "informational", "source_interface": "Vlan10", "timestamps_log": True},
        "snmp": {"communities": [{"name": "campusRO", "mode": "RO"}], "location": "College campus core"},
        "acls": [
            {"type": "standard", "number": 10, "rules": [{"action": "permit", "source": "10.0.0.0", "wildcard": "0.0.0.255"}]},
            {"type": "extended", "number": 101, "rules": [{"action": "permit", "protocol": "ip", "source": "10.0.0.0", "source_wildcard": "0.0.0.255", "destination": "any"}]},
        ],
        "nat": {"outside_interfaces": ["GigabitEthernet0/2"], "overloads": [{"acl": 10, "interface": "GigabitEthernet0/2"}]},
        "save": False,
    }
    return {
        "format": "pt730-ios-template",
        "packet_tracer_version": "7.3.0",
        "description": "High-level JSON surface rendered into IOS commands and optional pt730-topo ios_configs.",
        "fields": {
            "device": "Target Packet Tracer IOS device name.",
            "hostname": "Optional IOS hostname command.",
            "ip_routing": "True adds global ip routing for multilayer switches/routers.",
            "vlans": "Array of {id, name?}.",
            "interfaces": "Array of routed, access, or trunk interface declarations.",
            "interfaces[].mode=access": "Adds switchport mode access and switchport access vlan.",
            "interfaces[].mode=trunk": "Adds switchport mode trunk and switchport trunk allowed vlan.",
            "interfaces[].mode=routed": "Adds no switchport before interface IP configuration.",
            "interfaces[].ip": "Adds ip address; mask is required.",
            "interfaces[].helper_addresses": "Adds one or more ip helper-address DHCP relay commands.",
            "interfaces[].hsrp": "Object or array for standby/HSRP commands; supports group, ip, priority, preempt, timers, track.",
            "interfaces[].acl_in": "Adds ip access-group <value> in.",
            "interfaces[].acl_out": "Adds ip access-group <value> out.",
            "interfaces[].nat": "inside or outside; adds ip nat inside/outside.",
            "spanning_tree": "Optional STP mode/root/priority/default edge-port settings.",
            "spanning_tree.root_primary": "VLAN list for spanning-tree vlan <list> root primary.",
            "etherchannels": "Array of {group, mode, interfaces, port_channel?} for channel-group and Port-channel config.",
            "rip.networks": "RIPv2 network statements.",
            "ospf.networks": "OSPF network statements; each entry is {network, wildcard, area}.",
            "ospf.passive_interfaces": "Optional passive-interface commands for OSPF.",
            "static_routes": "Array of {destination, mask, next_hop|interface}.",
            "dhcp.excluded_addresses": "IOS DHCP excluded-address entries; string or {start,end}.",
            "dhcp.pools": "IOS DHCP pools with name, network, mask, default_router/gateway, dns_server/dns, domain_name/domain, lease.",
            "ntp.servers": "NTP server list; entries may be strings or {address, prefer, key, source, version}.",
            "logging.hosts": "Syslog host list plus trap/source_interface/timestamps_log/disable_console.",
            "snmp.communities": "SNMP community list with name/community, mode/access, and optional ACL.",
            "acls[].type=standard": "Numbered or named standard ACL rules.",
            "acls[].type=extended": "Extended ACL rules with protocol/source/destination wildcards.",
            "nat.overloads": "Array of {acl, interface} for PAT overload.",
            "devices": "Optional top-level array of device specs for multi-device topology-json output.",
        },
        "example": example,
    }


def render_commands(spec: dict[str, Any]) -> list[str]:
    device = str(require(spec.get("device", spec.get("name", "")), "device is required"))
    commands = ["enable", "configure terminal"]
    hostname = spec.get("hostname")
    if hostname:
        commands.append(f"hostname {hostname}")
    if spec.get("ip_routing"):
        commands.append("ip routing")
    if spec.get("no_ip_domain_lookup"):
        commands.append("no ip domain-lookup")

    for vlan in as_list(spec.get("vlans")):
        if not isinstance(vlan, dict):
            raise ValueError("vlan entries must be objects")
        vlan_id = require(vlan.get("id", vlan.get("vlan")), "vlan id is required")
        commands.append(f"vlan {vlan_id}")
        if vlan.get("name"):
            commands.append(f" name {vlan['name']}")
        commands.append("exit")

    spanning_tree = spec.get("spanning_tree")
    if isinstance(spanning_tree, dict):
        if spanning_tree.get("mode"):
            commands.append(f"spanning-tree mode {spanning_tree['mode']}")
        for key, role in (("root_primary", "primary"), ("root_secondary", "secondary")):
            value = spanning_tree.get(key)
            if value not in (None, "", []):
                commands.append(f"spanning-tree vlan {vlan_list(value)} root {role}")
        for entry in as_list(spanning_tree.get("vlan_priorities")):
            if not isinstance(entry, dict):
                raise ValueError("spanning_tree vlan_priorities entries must be objects")
            vlan = require(entry.get("vlan", entry.get("vlans")), "spanning_tree vlan priority vlan is required")
            priority = require(entry.get("priority"), "spanning_tree vlan priority value is required")
            commands.append(f"spanning-tree vlan {vlan_list(vlan)} priority {priority}")
        if spanning_tree.get("portfast_default"):
            commands.append("spanning-tree portfast default")
        if spanning_tree.get("bpduguard_default"):
            commands.append("spanning-tree bpduguard default")

    for interface in as_list(spec.get("interfaces")):
        if not isinstance(interface, dict):
            raise ValueError("interface entries must be objects")
        name = str(require(interface.get("name"), "interface name is required"))
        commands.append(f"interface {name}")
        if interface.get("description"):
            commands.append(f" description {interface['description']}")
        commands.extend(render_switchport_commands(interface))
        commands.extend(render_l3_interface_feature_commands(interface))
        acl_in = interface.get("acl_in", interface.get("access_group_in"))
        acl_out = interface.get("acl_out", interface.get("access_group_out"))
        if acl_in:
            commands.append(f" ip access-group {acl_in} in")
        if acl_out:
            commands.append(f" ip access-group {acl_out} out")
        if interface.get("nat") in ("inside", "outside"):
            commands.append(f" ip nat {interface['nat']}")
        if interface.get("shutdown") is True:
            commands.append(" shutdown")
        else:
            commands.append(" no shutdown")
        commands.append("exit")

    for etherchannel in as_list(spec.get("etherchannels")):
        if not isinstance(etherchannel, dict):
            raise ValueError("etherchannel entries must be objects")
        group = require(etherchannel.get("group", etherchannel.get("id")), "etherchannel group is required")
        channel_mode = str(etherchannel.get("mode", "active"))
        members = as_value_list(etherchannel.get("interfaces", etherchannel.get("members")))
        if not members:
            raise ValueError("etherchannel interfaces are required")
        for interface_name in members:
            commands.append(f"interface {interface_name}")
            commands.append(f" channel-group {group} mode {channel_mode}")
            commands.append(" no shutdown")
            commands.append("exit")
        port_channel = etherchannel.get("port_channel", etherchannel.get("portchannel", {}))
        if port_channel is None:
            port_channel = {}
        if not isinstance(port_channel, dict):
            raise ValueError("etherchannel port_channel must be an object")
        commands.append(f"interface {port_channel.get('name', f'Port-channel{group}')}")
        if port_channel.get("description"):
            commands.append(f" description {port_channel['description']}")
        commands.extend(render_switchport_commands(port_channel))
        commands.extend(render_l3_interface_feature_commands(port_channel))
        commands.append(" no shutdown")
        commands.append("exit")

    commands.extend(render_dhcp_commands(spec.get("dhcp")))
    commands.extend(render_ntp_commands(spec.get("ntp")))
    logging_spec = spec.get("logging") if "logging" in spec else spec.get("syslog")
    commands.extend(render_logging_commands(logging_spec))
    commands.extend(render_snmp_commands(spec.get("snmp")))

    rip = spec.get("rip")
    if isinstance(rip, dict):
        commands.append("router rip")
        if rip.get("version"):
            commands.append(f" version {rip['version']}")
        if rip.get("no_auto_summary", True):
            commands.append(" no auto-summary")
        for network in as_list(rip.get("networks")):
            commands.append(f" network {network}")
        commands.append("exit")

    ospf = spec.get("ospf")
    if isinstance(ospf, dict):
        process_id = ospf.get("process_id", ospf.get("process", 1))
        commands.append(f"router ospf {process_id}")
        if ospf.get("router_id"):
            commands.append(f" router-id {ospf['router_id']}")
        for interface_name in as_list(ospf.get("passive_interfaces")):
            commands.append(f" passive-interface {interface_name}")
        for network in as_list(ospf.get("networks")):
            if not isinstance(network, dict):
                raise ValueError("ospf network entries must be objects")
            area = network.get("area", 0)
            commands.append(
                f" network {require(network.get('network'), 'ospf network is required')} "
                f"{require(network.get('wildcard'), 'ospf wildcard is required')} area {area}"
            )
        commands.append("exit")

    for route in as_list(spec.get("static_routes")):
        if not isinstance(route, dict):
            raise ValueError("static route entries must be objects")
        commands.append(
            f"ip route {require(route.get('destination'), 'static route destination is required')} "
            f"{require(route.get('mask'), 'static route mask is required')} "
            f"{require(route.get('next_hop', route.get('interface')), 'static route next_hop/interface is required')}"
        )

    for acl in as_list(spec.get("acls")):
        if not isinstance(acl, dict):
            raise ValueError("acl entries must be objects")
        number = require(acl.get("number", acl.get("name")), "acl number/name is required")
        acl_type = str(acl.get("type", "standard")).lower()
        for rule in as_list(acl.get("rules")):
            if not isinstance(rule, dict):
                raise ValueError("acl rule entries must be objects")
            action = str(rule.get("action", "permit"))
            if acl_type == "extended":
                protocol = str(rule.get("protocol", "ip"))
                src = str(rule.get("source", "any"))
                src_wc = rule.get("source_wildcard")
                dst = str(rule.get("destination", "any"))
                dst_wc = rule.get("destination_wildcard")
                parts = ["access-list", str(number), action, protocol, src]
                if src != "any" and src_wc:
                    parts.append(str(src_wc))
                parts.append(dst)
                if dst != "any" and dst_wc:
                    parts.append(str(dst_wc))
                commands.append(" ".join(parts))
            else:
                source = str(rule.get("source", "any"))
                wildcard = rule.get("wildcard")
                line = f"access-list {number} {action} {source}"
                if source != "any" and wildcard:
                    line += f" {wildcard}"
                commands.append(line)

    nat = spec.get("nat")
    if isinstance(nat, dict):
        for interface_name in as_list(nat.get("inside_interfaces")):
            commands.extend([f"interface {interface_name}", " ip nat inside", "exit"])
        for interface_name in as_list(nat.get("outside_interfaces")):
            commands.extend([f"interface {interface_name}", " ip nat outside", "exit"])
        for overload in as_list(nat.get("overloads")):
            if not isinstance(overload, dict):
                raise ValueError("nat overload entries must be objects")
            commands.append(
                f"ip nat inside source list {require(overload.get('acl'), 'nat overload acl is required')} "
                f"interface {require(overload.get('interface'), 'nat overload interface is required')} overload"
            )

    commands.append("end")
    if spec.get("save", False):
        commands.append("write memory")
    if not device:
        raise ValueError("device is required")
    return commands


def render_records(spec: dict[str, Any]) -> list[dict[str, Any]]:
    devices = spec.get("devices")
    if devices is None:
        return [{"device": spec.get("device", spec.get("name")), "commands": render_commands(spec)}]
    if not isinstance(devices, list):
        raise ValueError("devices must be an array")
    records: list[dict[str, Any]] = []
    for index, device_spec in enumerate(devices):
        if not isinstance(device_spec, dict):
            raise ValueError(f"devices[{index}] must be an object")
        records.append({"device": device_spec.get("device", device_spec.get("name")), "commands": render_commands(device_spec)})
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("schema", help="print supported high-level IOS template JSON fields")
    render_p = sub.add_parser("render", help="render IOS commands")
    render_p.add_argument("spec", type=Path)
    render_p.add_argument("--topology-json", action="store_true", help="wrap commands in a pt730-topo ios_configs object")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "schema":
            print(json.dumps(schema_doc(), ensure_ascii=False, indent=2))
            return 0
        spec = load_json(args.spec)
        records = render_records(spec)
        if args.topology_json:
            print(json.dumps({"ios_configs": records}, ensure_ascii=False, indent=2))
        else:
            chunks = []
            for record in records:
                if len(records) > 1:
                    chunks.append(f"! device {record['device']}")
                chunks.append("\n".join(record["commands"]))
            print("\n".join(chunks))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"pt730-ios-template: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
