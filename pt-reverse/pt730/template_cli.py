#!/usr/bin/env python3
"""Generate built-in Packet Tracer 7.3.0 topology templates."""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
from itertools import islice
from pathlib import Path
from typing import Any

from compose_cli import compose_campus
from config_plan_cli import configured_plan
from layout_cli import LayoutOptions, STYLES, layout_plan


def _mask(network: ipaddress.IPv4Network) -> str:
    return str(network.netmask)


def _wildcard(network: ipaddress.IPv4Network) -> str:
    return str(network.hostmask)


def _host(network: ipaddress.IPv4Network, offset: int) -> ipaddress.IPv4Address:
    address = ipaddress.ip_address(int(network.network_address) + offset)
    if address not in network:
        raise ValueError(f"{network}: host offset {offset} is outside network")
    return address


def _emit(plan: dict[str, Any], output: Path | None, *, compact: bool) -> None:
    text = json.dumps(plan, ensure_ascii=False, indent=None if compact else 2, separators=(",", ":") if compact else None) + "\n"
    if output is None:
        print(text, end="")
        return
    output.write_text(text, encoding="utf-8")


def _maybe_layout(plan: dict[str, Any], *, style: str, no_layout: bool) -> dict[str, Any]:
    if no_layout:
        return plan
    return layout_plan(plan, LayoutOptions(style=style))


def schema() -> dict[str, Any]:
    return {
        "commands": ["schema", "lan-star", "wireless-lan", "vlan-router-on-stick", "edge-security", "router-ring", "wan-ring", "campus"],
        "templates": {
            "lan-star": {
                "description": "One router, one access switch, static PCs, optional HTTP servers.",
                "options": ["--name", "--pcs", "--servers", "--network", "--gateway", "--dns", "--layout-style", "--no-layout"],
            },
            "wireless-lan": {
                "description": "One router, one access switch, safe AccessPoint-PT APs, Laptop-PT clients, optional HTTP/DNS servers, and static host IPs.",
                "options": ["--name", "--aps", "--laptops", "--servers", "--network", "--gateway", "--dns", "--ssid", "--layout-style", "--no-layout"],
            },
            "vlan-router-on-stick": {
                "description": "One 2911 router, one 2960 switch, 802.1Q trunk, router subinterfaces, access VLANs, static hosts, and optional HTTP/DNS servers.",
                "options": ["--name", "--vlans", "--hosts-per-vlan", "--servers-per-vlan", "--address-pool", "--vlan-prefix", "--vlan-base", "--native-vlan", "--domain", "--layout-style", "--no-layout"],
            },
            "edge-security": {
                "description": "ISP edge router, inside LAN, DMZ servers, Internet test host, NAT overload, outside ACL, and static routes.",
                "options": ["--name", "--inside-hosts", "--dmz-servers", "--internet-hosts", "--inside-network", "--dmz-network", "--wan-network", "--internet-network", "--domain", "--layout-style", "--no-layout"],
            },
            "router-ring": {
                "description": "Serial WAN ring of 2911 routers with HWIC-2T modules and RIPv2 configs.",
                "options": ["--name", "--routers", "--interconnect-pool", "--layout-style", "--no-layout"],
            },
            "wan-ring": {
                "description": "Serial multi-site WAN ring with one access LAN per site, representative PCs/servers, HTTP/DNS services, and optional RIP/static routing.",
                "options": ["--name", "--sites", "--hosts-per-site", "--servers-per-site", "--interconnect-pool", "--lan-pool", "--lan-prefix", "--routing none|rip|static", "--layout-style", "--no-layout"],
            },
            "campus": {
                "description": "Core-switch campus with server VLAN, access VLANs, representative hosts, services, optional L3 IOS configs.",
                "options": ["--name", "--cores", "--segments", "--hosts-per-segment", "--access-switches-per-segment", "--servers", "--address-pool", "--segment-prefix", "--server-network", "--server-vlan", "--vlan-base", "--interconnect-pool", "--l3", "--routing none|rip|static", "--layout-style", "--no-layout"],
            },
        },
    }


def lan_star(*, name: str, pcs: int, servers: int, network: str, gateway: str | None, dns: str | None, layout_style: str, no_layout: bool) -> dict[str, Any]:
    if pcs < 0 or servers < 0:
        raise ValueError("pcs and servers must be >= 0")
    if pcs + servers < 1:
        raise ValueError("lan-star requires at least one PC or server")
    net = ipaddress.ip_network(network, strict=False)
    gw = ipaddress.ip_address(gateway) if gateway else _host(net, 1)
    if gw not in net:
        raise ValueError(f"gateway {gw} is outside {net}")
    if net.num_addresses < pcs + servers + 3:
        raise ValueError(f"{net}: not enough addresses for requested hosts")

    slug = name.upper()
    router = f"R-{slug}"
    switch = f"SW-{slug}"
    plan: dict[str, Any] = {
        "devices": [
            {"name": router, "category": "router", "model": "2911"},
            {"name": switch, "category": "switch", "model": "2960-24TT"},
        ],
        "links": [{"a": router, "pa": "GigabitEthernet0/0", "b": switch, "pb": "FastEthernet0/1", "cable": "straight"}],
        "pc_configs": [],
        "server_configs": [],
        "ios_configs": [
            {
                "device": router,
                "init_dialog": True,
                "commands": [
                    "enable",
                    "configure terminal",
                    f"hostname {router}",
                    "interface GigabitEthernet0/0",
                    f"ip address {gw} {_mask(net)}",
                    "no shutdown",
                    "end",
                ],
            }
        ],
        "metadata": {"source": "pt730-template lan-star", "name": name, "network": str(net)},
    }

    next_offset = 2 if gw == _host(net, 1) else 1
    for index in range(1, pcs + 1):
        host = f"PC-{slug}-{index}"
        ip_addr = _host(net, next_offset)
        while ip_addr == gw:
            next_offset += 1
            ip_addr = _host(net, next_offset)
        next_offset += 1
        plan["devices"].append({"name": host, "category": "pc", "model": "PC-PT"})
        plan["links"].append({"a": switch, "pa": f"FastEthernet0/{len(plan['links']) + 1}", "b": host, "pb": "FastEthernet0", "cable": "straight"})
        plan["pc_configs"].append({"name": host, "port": "FastEthernet0", "ip": str(ip_addr), "mask": _mask(net), "gateway": str(gw), "dns": dns or ""})

    for index in range(1, servers + 1):
        server = f"SRV-{slug}-{index}"
        ip_addr = _host(net, next_offset)
        while ip_addr == gw:
            next_offset += 1
            ip_addr = _host(net, next_offset)
        next_offset += 1
        plan["devices"].append({"name": server, "category": "server", "model": "Server-PT"})
        plan["links"].append({"a": switch, "pa": f"FastEthernet0/{len(plan['links']) + 1}", "b": server, "pb": "FastEthernet0", "cable": "straight"})
        plan["pc_configs"].append({"name": server, "port": "FastEthernet0", "ip": str(ip_addr), "mask": _mask(net), "gateway": str(gw), "dns": dns or str(ip_addr)})
        plan["server_configs"].append({"name": server, "http": True})

    return _maybe_layout(plan, style=layout_style, no_layout=no_layout)


def wireless_lan(
    *,
    name: str,
    aps: int,
    laptops: int,
    servers: int,
    network: str,
    gateway: str | None,
    dns: str | None,
    ssid: str,
    layout_style: str,
    no_layout: bool,
) -> dict[str, Any]:
    if aps < 1:
        raise ValueError("wireless-lan requires at least one AP")
    if laptops < 0 or servers < 0:
        raise ValueError("laptops and servers must be >= 0")
    if laptops + servers < 1:
        raise ValueError("wireless-lan requires at least one laptop or server")
    if aps + servers > 23:
        raise ValueError("wireless-lan supports up to 23 AP/server uplinks on one 2960 access switch")
    net = ipaddress.ip_network(network, strict=False)
    gw = ipaddress.ip_address(gateway) if gateway else _host(net, 1)
    if gw not in net:
        raise ValueError(f"gateway {gw} is outside {net}")
    host_addresses = _host_list(net, count=laptops + servers, skip={gw})
    server_addresses = host_addresses[laptops:]
    dns_ip = dns or (str(server_addresses[0]) if server_addresses else "")
    slug = name.upper()
    router = f"R-{slug}"
    switch = f"SW-{slug}"

    plan: dict[str, Any] = {
        "devices": [
            {"name": router, "category": "router", "model": "2911"},
            {"name": switch, "category": "switch", "model": "2960-24TT"},
        ],
        "links": [{"a": router, "pa": "GigabitEthernet0/0", "b": switch, "pb": "FastEthernet0/1", "cable": "straight", "note": "wired gateway"}],
        "pc_configs": [],
        "server_configs": [],
        "ap_configs": [],
        "ios_configs": [
            {
                "device": router,
                "init_dialog": True,
                "commands": [
                    "enable",
                    "configure terminal",
                    f"hostname {router}",
                    "interface GigabitEthernet0/0",
                    f"ip address {gw} {_mask(net)}",
                    "no shutdown",
                    "end",
                ],
            }
        ],
        "metadata": {"source": "pt730-template wireless-lan", "name": name, "network": str(net), "ssid": ssid},
    }

    ap_names: list[str] = []
    for index in range(1, aps + 1):
        ap = f"AP-{slug}-{index}"
        ap_names.append(ap)
        plan["devices"].append({"name": ap, "category": "accesspoint", "model": "AccessPoint-PT", "ssid": ssid})
        plan["links"].append({"a": switch, "pa": f"FastEthernet0/{index + 1}", "b": ap, "pb": "Port 0", "cable": "straight", "note": f"AP uplink SSID {ssid}"})
        plan["ap_configs"].append({"name": ap, "ssid": ssid, "mode": "access-point", "note": "offline metadata only; live AP configuration remains guarded"})

    for index, address in enumerate(host_addresses[:laptops], start=1):
        laptop = f"LAP-{slug}-{index}"
        ap = ap_names[(index - 1) % len(ap_names)]
        plan["devices"].append({"name": laptop, "category": "laptop", "model": "Laptop-PT", "ssid": ssid})
        plan["links"].append({"a": ap, "pa": "Port 0", "b": laptop, "pb": "FastEthernet0", "cable": "wireless", "note": f"wireless association SSID {ssid}"})
        plan["pc_configs"].append({"name": laptop, "port": "FastEthernet0", "ip": str(address), "mask": _mask(net), "gateway": str(gw), "dns": dns_ip})

    for index, address in enumerate(server_addresses, start=1):
        server = f"SRV-{slug}-{index}"
        plan["devices"].append({"name": server, "category": "server", "model": "Server-PT"})
        plan["links"].append({"a": switch, "pa": f"FastEthernet0/{aps + index + 1}", "b": server, "pb": "FastEthernet0", "cable": "straight", "note": "wired service host"})
        plan["pc_configs"].append({"name": server, "port": "FastEthernet0", "ip": str(address), "mask": _mask(net), "gateway": str(gw), "dns": dns_ip or str(address)})
        services: dict[str, Any] = {"http": True}
        if index == 1:
            services["dns"] = {"enabled": True, "records": [{"name": f"wifi.{name.lower()}.local", "ip": str(address)}]}
        plan["server_configs"].append({"name": server, **services})

    return _maybe_layout(plan, style=layout_style, no_layout=no_layout)


def _rip_network(address: ipaddress.IPv4Address) -> str:
    octets = str(address).split(".")
    first = int(octets[0])
    if first < 128:
        return f"{octets[0]}.0.0.0"
    if first < 192:
        return f"{octets[0]}.{octets[1]}.0.0"
    return f"{octets[0]}.{octets[1]}.{octets[2]}.0"


def router_ring(*, name: str, routers: int, interconnect_pool: str, layout_style: str, no_layout: bool) -> dict[str, Any]:
    if routers < 2:
        raise ValueError("router-ring requires at least two routers")
    pool = ipaddress.ip_network(interconnect_pool, strict=False)
    subnets = list(pool.subnets(new_prefix=30))
    if len(subnets) < routers:
        raise ValueError(f"{pool}: not enough /30 subnets for {routers} ring links")
    slug = name.upper()
    names = [f"R-{slug}-{index}" for index in range(1, routers + 1)]
    plan: dict[str, Any] = {
        "devices": [{"name": router, "category": "router", "model": "2911"} for router in names],
        "modules": [{"device": router, "slot": "0/0", "model": "HWIC-2T"} for router in names],
        "links": [],
        "pc_configs": [],
        "ios_configs": [],
        "metadata": {"source": "pt730-template router-ring", "name": name, "interconnect_pool": str(pool)},
    }
    configs: dict[str, list[str]] = {
        router: ["enable", "configure terminal", f"hostname {router}"] for router in names
    }
    rip_networks: set[str] = set()

    for index, subnet in enumerate(subnets[:routers]):
        a = names[index]
        b = names[(index + 1) % routers]
        hosts = list(subnet.hosts())
        a_ip = hosts[0]
        b_ip = hosts[1]
        a_port = "Serial0/0/0"
        b_port = "Serial0/0/1"
        plan["links"].append({"a": a, "pa": a_port, "b": b, "pb": b_port, "cable": "serial", "note": str(subnet)})
        configs[a].extend(["interface " + a_port, f"ip address {a_ip} {_mask(subnet)}", "clock rate 64000", "no shutdown", "exit"])
        configs[b].extend(["interface " + b_port, f"ip address {b_ip} {_mask(subnet)}", "no shutdown", "exit"])
        rip_networks.add(_rip_network(a_ip))
        rip_networks.add(_rip_network(b_ip))

    for router in names:
        commands = configs[router]
        commands.extend(["router rip", "version 2", "no auto-summary"])
        for network in sorted(rip_networks, key=lambda value: tuple(int(part) for part in value.split("."))):
            commands.append(f"network {network}")
        commands.extend(["exit", "end"])
        plan["ios_configs"].append({"device": router, "init_dialog": True, "commands": commands})

    return _maybe_layout(plan, style=layout_style, no_layout=no_layout)


def _subnets(pool: ipaddress.IPv4Network, prefix: int, count: int, *, label: str) -> list[ipaddress.IPv4Network]:
    if count < 0:
        raise ValueError(f"{label}: count must be >= 0")
    if prefix < pool.prefixlen or prefix > 32:
        raise ValueError(f"{label}: prefix must be between {pool.prefixlen} and 32")
    networks = list(islice(pool.subnets(new_prefix=prefix), count))
    if len(networks) < count:
        raise ValueError(f"{pool}: not enough /{prefix} subnets for {count} segment(s)")
    return networks


def _last_gateway(network: ipaddress.IPv4Network) -> ipaddress.IPv4Address:
    if network.num_addresses > 2:
        return ipaddress.ip_address(int(network.broadcast_address) - 1)
    hosts = list(network.hosts())
    if not hosts:
        raise ValueError(f"{network}: no usable gateway address")
    return hosts[-1]


def _host_list(network: ipaddress.IPv4Network, *, count: int, skip: set[ipaddress.IPv4Address]) -> list[ipaddress.IPv4Address]:
    result: list[ipaddress.IPv4Address] = []
    for address in network.hosts():
        if address in skip:
            continue
        result.append(address)
        if len(result) >= count:
            return result
    raise ValueError(f"{network}: not enough usable host addresses")


def vlan_router_on_stick(
    *,
    name: str,
    vlans: int,
    hosts_per_vlan: int,
    servers_per_vlan: int,
    address_pool: str,
    vlan_prefix: int,
    vlan_base: int,
    native_vlan: int | None,
    domain: str,
    layout_style: str,
    no_layout: bool,
) -> dict[str, Any]:
    if vlans < 1:
        raise ValueError("vlan-router-on-stick requires at least one VLAN")
    if hosts_per_vlan < 0 or servers_per_vlan < 0:
        raise ValueError("hosts-per-vlan and servers-per-vlan must be >= 0")
    if hosts_per_vlan + servers_per_vlan < 1:
        raise ValueError("vlan-router-on-stick requires at least one host or server per VLAN")
    endpoints = vlans * (hosts_per_vlan + servers_per_vlan)
    if endpoints > 24:
        raise ValueError("vlan-router-on-stick supports up to 24 access endpoints on one 2960 switch")
    vlan_ids = [vlan_base + index for index in range(vlans)]
    if native_vlan is not None and native_vlan not in vlan_ids:
        raise ValueError("native-vlan must match one of the generated VLAN IDs")

    pool = ipaddress.ip_network(address_pool, strict=False)
    networks = _subnets(pool, vlan_prefix, vlans, label="vlan-prefix")
    slug = name.upper()
    router = f"R-{slug}" if slug.endswith("ROAS") else f"R-{slug}-ROAS"
    switch = f"SW-{slug}-ACCESS"
    allowed_vlans = ",".join(str(vlan_id) for vlan_id in vlan_ids)

    router_commands = [
        "enable",
        "configure terminal",
        f"hostname {router}",
        "interface GigabitEthernet0/0",
        "description 802.1Q_TRUNK_TO_ACCESS_SWITCH",
        "no shutdown",
        "exit",
    ]
    switch_commands = [
        "enable",
        "configure terminal",
        f"hostname {switch}",
    ]
    plan: dict[str, Any] = {
        "devices": [
            {"name": router, "category": "router", "model": "2911"},
            {"name": switch, "category": "switch", "model": "2960-24TT"},
        ],
        "links": [
            {
                "a": router,
                "pa": "GigabitEthernet0/0",
                "b": switch,
                "pb": "GigabitEthernet0/1",
                "cable": "straight",
                "note": f"802.1Q trunk VLANs {allowed_vlans}",
            }
        ],
        "pc_configs": [],
        "server_configs": [],
        "vlan_configs": [],
        "ios_configs": [],
        "metadata": {
            "source": "pt730-template vlan-router-on-stick",
            "name": name,
            "address_pool": str(pool),
            "vlan_base": vlan_base,
            "native_vlan": native_vlan,
            "domain": domain,
        },
    }

    vlan_infos: list[dict[str, Any]] = []
    first_server_by_vlan: dict[int, str] = {}
    for index, (vlan_id, network) in enumerate(zip(vlan_ids, networks), start=1):
        gateway = _host(network, 1)
        addresses = _host_list(network, count=hosts_per_vlan + servers_per_vlan, skip={gateway})
        vlan_name = f"VLAN{vlan_id}"
        vlan_infos.append({"id": vlan_id, "name": vlan_name, "network": network, "gateway": gateway, "addresses": addresses})
        plan["vlan_configs"].append({"id": vlan_id, "name": vlan_name, "network": str(network), "gateway": str(gateway)})

    for info in vlan_infos:
        vlan_id = info["id"]
        switch_commands.extend(["vlan " + str(vlan_id), f"name {info['name']}", "exit"])
        router_commands.extend(
            [
                f"interface GigabitEthernet0/0.{vlan_id}",
                f"description Gateway_for_{info['name']}",
                f"encapsulation dot1Q {vlan_id}" + (" native" if native_vlan == vlan_id else ""),
                f"ip address {info['gateway']} {_mask(info['network'])}",
                "no shutdown",
                "exit",
            ]
        )

    switch_commands.extend(
        [
            "interface GigabitEthernet0/1",
            "description TRUNK_TO_ROUTER",
            "switchport mode trunk",
            f"switchport trunk allowed vlan {allowed_vlans}",
        ]
    )
    if native_vlan is not None:
        switch_commands.append(f"switchport trunk native vlan {native_vlan}")
    switch_commands.extend(["no shutdown", "exit"])

    next_port = 1
    dns_ip = ""
    if servers_per_vlan:
        first_server_address = vlan_infos[0]["addresses"][hosts_per_vlan]
        dns_ip = str(first_server_address)

    dns_records: list[dict[str, str]] = []
    dns_server_name = ""
    for vlan_index, info in enumerate(vlan_infos, start=1):
        vlan_id = info["id"]
        network = info["network"]
        gateway = info["gateway"]
        addresses = info["addresses"]
        for host_index, address in enumerate(addresses[:hosts_per_vlan], start=1):
            host = f"PC-{slug}-V{vlan_id}-{host_index}"
            port = f"FastEthernet0/{next_port}"
            next_port += 1
            plan["devices"].append({"name": host, "category": "pc", "model": "PC-PT", "vlan": vlan_id})
            plan["links"].append({"a": switch, "pa": port, "b": host, "pb": "FastEthernet0", "cable": "straight", "vlan": vlan_id, "note": f"access VLAN {vlan_id}"})
            plan["pc_configs"].append({"name": host, "port": "FastEthernet0", "ip": str(address), "mask": _mask(network), "gateway": str(gateway), "dns": dns_ip})
            switch_commands.extend(["interface " + port, f"description ACCESS_VLAN_{vlan_id}", "switchport mode access", f"switchport access vlan {vlan_id}", "spanning-tree portfast", "no shutdown", "exit"])

        for server_index, address in enumerate(addresses[hosts_per_vlan:], start=1):
            server = f"SRV-{slug}-V{vlan_id}-{server_index}"
            port = f"FastEthernet0/{next_port}"
            next_port += 1
            plan["devices"].append({"name": server, "category": "server", "model": "Server-PT", "vlan": vlan_id})
            plan["links"].append({"a": switch, "pa": port, "b": server, "pb": "FastEthernet0", "cable": "straight", "vlan": vlan_id, "note": f"server VLAN {vlan_id}"})
            plan["pc_configs"].append({"name": server, "port": "FastEthernet0", "ip": str(address), "mask": _mask(network), "gateway": str(gateway), "dns": dns_ip or str(address)})
            services: dict[str, Any] = {"http": True}
            dns_records.append({"name": f"vlan{vlan_id}.{domain}", "ip": str(address)})
            if not dns_server_name:
                dns_server_name = server
                services["dns"] = {"enabled": True, "records": dns_records}
            plan["server_configs"].append({"name": server, **services})
            first_server_by_vlan[vlan_id] = str(address)
            switch_commands.extend(["interface " + port, f"description SERVER_VLAN_{vlan_id}", "switchport mode access", f"switchport access vlan {vlan_id}", "spanning-tree portfast", "no shutdown", "exit"])

    if dns_server_name:
        for config in plan["server_configs"]:
            if config["name"] == dns_server_name:
                config["dns"] = {"enabled": True, "records": dns_records}
                break

    router_commands.append("end")
    switch_commands.append("end")
    plan["ios_configs"] = [
        {"device": router, "init_dialog": True, "commands": router_commands},
        {"device": switch, "init_dialog": True, "commands": switch_commands},
    ]
    plan["metadata"]["server_gateways"] = first_server_by_vlan
    return _maybe_layout(plan, style=layout_style, no_layout=no_layout)


def edge_security(
    *,
    name: str,
    inside_hosts: int,
    dmz_servers: int,
    internet_hosts: int,
    inside_network: str,
    dmz_network: str,
    wan_network: str,
    internet_network: str,
    domain: str,
    layout_style: str,
    no_layout: bool,
) -> dict[str, Any]:
    if inside_hosts < 1:
        raise ValueError("edge-security requires at least one inside host")
    if dmz_servers < 1:
        raise ValueError("edge-security requires at least one DMZ server")
    if internet_hosts < 1:
        raise ValueError("edge-security requires at least one Internet test host")
    if inside_hosts > 23 or dmz_servers > 23 or internet_hosts > 23:
        raise ValueError("edge-security supports up to 23 hosts per access switch")

    inside_net = ipaddress.ip_network(inside_network, strict=False)
    dmz_net = ipaddress.ip_network(dmz_network, strict=False)
    wan_net = ipaddress.ip_network(wan_network, strict=False)
    inet_net = ipaddress.ip_network(internet_network, strict=False)
    if len(list(wan_net.hosts())) < 2:
        raise ValueError(f"{wan_net}: WAN network needs at least two usable hosts")

    inside_gw = _host(inside_net, 1)
    dmz_gw = _host(dmz_net, 1)
    isp_wan = _host(wan_net, 1)
    edge_wan = _host(wan_net, 2)
    inet_gw = _host(inet_net, 1)
    inside_addresses = _host_list(inside_net, count=inside_hosts, skip={inside_gw})
    dmz_addresses = _host_list(dmz_net, count=dmz_servers, skip={dmz_gw})
    internet_addresses = _host_list(inet_net, count=internet_hosts, skip={inet_gw})

    slug = name.upper()
    edge = f"R-{slug}-EDGE"
    isp = f"R-{slug}-ISP"
    lan_switch = f"SW-{slug}-LAN"
    dmz_switch = f"SW-{slug}-DMZ"
    internet_switch = f"SW-{slug}-INET"
    web_ip = dmz_addresses[0]
    dns_ip = dmz_addresses[1] if len(dmz_addresses) > 1 else dmz_addresses[0]
    dns_records = [
        {"name": f"www.{domain}", "ip": str(web_ip)},
        {"name": f"dns.{domain}", "ip": str(dns_ip)},
    ]

    edge_commands = [
        "enable",
        "configure terminal",
        f"hostname {edge}",
        "interface GigabitEthernet0/0",
        "description INSIDE_LAN",
        f"ip address {inside_gw} {_mask(inside_net)}",
        "ip nat inside",
        "no shutdown",
        "exit",
        "interface GigabitEthernet0/1",
        "description DMZ",
        f"ip address {dmz_gw} {_mask(dmz_net)}",
        "no shutdown",
        "exit",
        "interface GigabitEthernet0/2",
        "description OUTSIDE_TO_ISP",
        f"ip address {edge_wan} {_mask(wan_net)}",
        "ip nat outside",
        "ip access-group 101 in",
        "no shutdown",
        "exit",
        f"ip route 0.0.0.0 0.0.0.0 {isp_wan}",
        f"access-list 10 permit {inside_net.network_address} {_wildcard(inside_net)}",
        f"access-list 101 permit tcp any host {web_ip} eq 80",
        f"access-list 101 permit icmp any host {web_ip}",
        f"access-list 101 permit udp any host {dns_ip} eq 53",
        f"access-list 101 deny ip any {inside_net.network_address} {_wildcard(inside_net)}",
        "access-list 101 permit ip any any",
        "ip nat inside source list 10 interface GigabitEthernet0/2 overload",
        "end",
    ]
    isp_commands = [
        "enable",
        "configure terminal",
        f"hostname {isp}",
        "interface GigabitEthernet0/0",
        "description WAN_TO_EDGE",
        f"ip address {isp_wan} {_mask(wan_net)}",
        "no shutdown",
        "exit",
        "interface GigabitEthernet0/1",
        "description INTERNET_TEST_NET",
        f"ip address {inet_gw} {_mask(inet_net)}",
        "no shutdown",
        "exit",
        f"ip route {inside_net.network_address} {_mask(inside_net)} {edge_wan}",
        f"ip route {dmz_net.network_address} {_mask(dmz_net)} {edge_wan}",
        "end",
    ]

    plan: dict[str, Any] = {
        "devices": [
            {"name": edge, "category": "router", "model": "2911"},
            {"name": isp, "category": "router", "model": "2911"},
            {"name": lan_switch, "category": "switch", "model": "2960-24TT"},
            {"name": dmz_switch, "category": "switch", "model": "2960-24TT"},
            {"name": internet_switch, "category": "switch", "model": "2960-24TT"},
        ],
        "links": [
            {"a": edge, "pa": "GigabitEthernet0/0", "b": lan_switch, "pb": "FastEthernet0/1", "cable": "straight", "note": "inside LAN"},
            {"a": edge, "pa": "GigabitEthernet0/1", "b": dmz_switch, "pb": "FastEthernet0/1", "cable": "straight", "note": "DMZ"},
            {"a": edge, "pa": "GigabitEthernet0/2", "b": isp, "pb": "GigabitEthernet0/0", "cable": "cross", "note": str(wan_net), "l3_subnet": str(wan_net)},
            {"a": isp, "pa": "GigabitEthernet0/1", "b": internet_switch, "pb": "FastEthernet0/1", "cable": "straight", "note": "Internet test LAN"},
        ],
        "pc_configs": [],
        "server_configs": [],
        "security_policies": [
            {
                "device": edge,
                "type": "nat_overload",
                "interface": "GigabitEthernet0/2",
                "acl": "10",
                "direction": "inside-to-outside",
                "summary": f"PAT inside {inside_net} to outside interface {edge_wan}",
            },
            {
                "device": edge,
                "type": "outside_acl",
                "interface": "GigabitEthernet0/2",
                "acl": "101",
                "direction": "in",
                "summary": f"Permit HTTP/ICMP to {web_ip}, DNS to {dns_ip}, deny inbound to {inside_net}",
            },
        ],
        "ios_configs": [
            {"device": edge, "init_dialog": True, "commands": edge_commands},
            {"device": isp, "init_dialog": True, "commands": isp_commands},
        ],
        "metadata": {
            "source": "pt730-template edge-security",
            "name": name,
            "inside_network": str(inside_net),
            "dmz_network": str(dmz_net),
            "wan_network": str(wan_net),
            "internet_network": str(inet_net),
            "domain": domain,
        },
    }

    for index, address in enumerate(inside_addresses, start=1):
        host = f"PC-{slug}-IN-{index}"
        plan["devices"].append({"name": host, "category": "pc", "model": "PC-PT"})
        plan["links"].append({"a": lan_switch, "pa": f"FastEthernet0/{index + 1}", "b": host, "pb": "FastEthernet0", "cable": "straight", "note": "inside host"})
        plan["pc_configs"].append({"name": host, "port": "FastEthernet0", "ip": str(address), "mask": _mask(inside_net), "gateway": str(inside_gw), "dns": str(dns_ip)})

    for index, address in enumerate(dmz_addresses, start=1):
        if index == 1:
            server = f"SRV-{slug}-WEB"
            services: dict[str, Any] = {"http": True}
        elif index == 2:
            server = f"SRV-{slug}-DNS"
            services = {"dns": {"enabled": True, "records": dns_records}}
        else:
            server = f"SRV-{slug}-DMZ-{index}"
            services = {"http": True}
        if dmz_servers == 1:
            services["dns"] = {"enabled": True, "records": dns_records}
        plan["devices"].append({"name": server, "category": "server", "model": "Server-PT"})
        plan["links"].append({"a": dmz_switch, "pa": f"FastEthernet0/{index + 1}", "b": server, "pb": "FastEthernet0", "cable": "straight", "note": "DMZ service"})
        plan["pc_configs"].append({"name": server, "port": "FastEthernet0", "ip": str(address), "mask": _mask(dmz_net), "gateway": str(dmz_gw), "dns": str(dns_ip)})
        plan["server_configs"].append({"name": server, **services})

    for index, address in enumerate(internet_addresses, start=1):
        host = f"PC-{slug}-INET-{index}"
        plan["devices"].append({"name": host, "category": "pc", "model": "PC-PT"})
        plan["links"].append({"a": internet_switch, "pa": f"FastEthernet0/{index + 1}", "b": host, "pb": "FastEthernet0", "cable": "straight", "note": "Internet test host"})
        plan["pc_configs"].append({"name": host, "port": "FastEthernet0", "ip": str(address), "mask": _mask(inet_net), "gateway": str(inet_gw), "dns": str(dns_ip)})

    return _maybe_layout(plan, style=layout_style, no_layout=no_layout)


def wan_ring(
    *,
    name: str,
    sites: int,
    hosts_per_site: int,
    servers_per_site: int,
    interconnect_pool: str,
    lan_pool: str,
    lan_prefix: int,
    routing: str,
    layout_style: str,
    no_layout: bool,
) -> dict[str, Any]:
    if sites < 2:
        raise ValueError("wan-ring requires at least two sites")
    if hosts_per_site < 0 or servers_per_site < 0:
        raise ValueError("hosts-per-site and servers-per-site must be >= 0")
    if hosts_per_site + servers_per_site > 23:
        raise ValueError("wan-ring supports up to 23 hosts/servers per site on one 2960 access switch")

    serial_pool = ipaddress.ip_network(interconnect_pool, strict=False)
    serial_subnets = _subnets(serial_pool, 30, sites, label="interconnect-pool")
    lan_supernet = ipaddress.ip_network(lan_pool, strict=False)
    lan_subnets = _subnets(lan_supernet, lan_prefix, sites, label="lan-prefix")
    slug = name.upper()
    routers = [f"R-{slug}-{index}" for index in range(1, sites + 1)]

    site_infos: list[dict[str, Any]] = []
    for index, network in enumerate(lan_subnets, start=1):
        gateway = _host(network, 1)
        addresses = _host_list(network, count=hosts_per_site + servers_per_site, skip={gateway})
        site_infos.append(
            {
                "index": index,
                "network": network,
                "gateway": gateway,
                "host_addresses": addresses[:hosts_per_site],
                "server_addresses": addresses[hosts_per_site:],
            }
        )

    dns_ip = ""
    for site in site_infos:
        if site["server_addresses"]:
            dns_ip = str(site["server_addresses"][0])
            break

    plan: dict[str, Any] = {
        "devices": [{"name": router, "category": "router", "model": "2911"} for router in routers],
        "modules": [{"device": router, "slot": "0/0", "model": "HWIC-2T"} for router in routers],
        "links": [],
        "pc_configs": [],
        "server_configs": [],
        "ios_configs": [],
        "metadata": {
            "source": "pt730-template wan-ring",
            "name": name,
            "interconnect_pool": str(serial_pool),
            "lan_pool": str(lan_supernet),
        },
    }
    configs: dict[str, list[str]] = {
        router: ["enable", "configure terminal", f"hostname {router}"] for router in routers
    }
    rip_networks: set[str] = set()
    clockwise_next_hop: dict[str, ipaddress.IPv4Address] = {}
    server_configs_by_name: dict[str, dict[str, Any]] = {}
    dns_records: list[dict[str, str]] = []
    dns_server_name = ""

    for router, site in zip(routers, site_infos):
        site_index = site["index"]
        network = site["network"]
        gateway = site["gateway"]
        switch = f"SW-{slug}-{site_index}"
        plan["devices"].append({"name": switch, "category": "switch", "model": "2960-24TT"})
        plan["links"].append({"a": router, "pa": "GigabitEthernet0/0", "b": switch, "pb": "FastEthernet0/1", "cable": "straight", "note": f"site {site_index} LAN"})
        configs[router].extend(["interface GigabitEthernet0/0", f"ip address {gateway} {_mask(network)}", "no shutdown", "exit"])
        rip_networks.add(_rip_network(gateway))

        next_switch_port = 2
        for host_index, address in enumerate(site["host_addresses"], start=1):
            host = f"PC-{slug}-{site_index}-{host_index}"
            plan["devices"].append({"name": host, "category": "pc", "model": "PC-PT"})
            plan["links"].append({"a": switch, "pa": f"FastEthernet0/{next_switch_port}", "b": host, "pb": "FastEthernet0", "cable": "straight", "note": f"site {site_index} host"})
            next_switch_port += 1
            plan["pc_configs"].append({"name": host, "port": "FastEthernet0", "ip": str(address), "mask": _mask(network), "gateway": str(gateway), "dns": dns_ip})

        for server_index, address in enumerate(site["server_addresses"], start=1):
            server = f"SRV-{slug}-{site_index}-{server_index}"
            plan["devices"].append({"name": server, "category": "server", "model": "Server-PT"})
            plan["links"].append({"a": switch, "pa": f"FastEthernet0/{next_switch_port}", "b": server, "pb": "FastEthernet0", "cable": "straight", "note": f"site {site_index} server"})
            next_switch_port += 1
            plan["pc_configs"].append({"name": server, "port": "FastEthernet0", "ip": str(address), "mask": _mask(network), "gateway": str(gateway), "dns": dns_ip or str(address)})
            server_configs_by_name[server] = {"name": server, "http": True}
            dns_records.append({"name": f"www.site{site_index}.{name.lower()}.local", "ip": str(address)})
            if not dns_server_name:
                dns_server_name = server

    if dns_server_name:
        server_configs_by_name[dns_server_name]["dns"] = {"enabled": True, "records": dns_records}
    plan["server_configs"] = list(server_configs_by_name.values())

    for index, subnet in enumerate(serial_subnets):
        a = routers[index]
        b = routers[(index + 1) % sites]
        hosts = list(subnet.hosts())
        a_ip = hosts[0]
        b_ip = hosts[1]
        a_port = "Serial0/0/0"
        b_port = "Serial0/0/1"
        plan["links"].append({"a": a, "pa": a_port, "b": b, "pb": b_port, "cable": "serial", "note": str(subnet), "l3_subnet": str(subnet)})
        configs[a].extend(["interface " + a_port, f"ip address {a_ip} {_mask(subnet)}", "clock rate 64000", "no shutdown", "exit"])
        configs[b].extend(["interface " + b_port, f"ip address {b_ip} {_mask(subnet)}", "no shutdown", "exit"])
        clockwise_next_hop[a] = b_ip
        rip_networks.add(_rip_network(a_ip))
        rip_networks.add(_rip_network(b_ip))

    for router_index, router in enumerate(routers):
        commands = configs[router]
        if routing == "rip":
            commands.extend(["router rip", "version 2", "no auto-summary"])
            for network in sorted(rip_networks, key=lambda value: tuple(int(part) for part in value.split("."))):
                commands.append(f"network {network}")
            commands.append("exit")
        elif routing == "static":
            next_hop = clockwise_next_hop[router]
            for lan_index, network in enumerate(lan_subnets):
                if lan_index == router_index:
                    continue
                commands.append(f"ip route {network.network_address} {network.netmask} {next_hop}")
        commands.append("end")
        plan["ios_configs"].append({"device": router, "init_dialog": True, "commands": commands})

    return _maybe_layout(plan, style=layout_style, no_layout=no_layout)


def campus(
    *,
    name: str,
    cores: int,
    segments: int,
    hosts_per_segment: int,
    access_switches_per_segment: int,
    servers: int,
    address_pool: str,
    segment_prefix: int,
    server_network: str,
    server_vlan: int,
    vlan_base: int,
    interconnect_pool: str,
    layout_style: str,
    no_layout: bool,
    l3: bool,
    routing: str,
) -> dict[str, Any]:
    if cores < 1:
        raise ValueError("campus requires at least one core switch")
    if segments < 1:
        raise ValueError("campus requires at least one access segment")
    if hosts_per_segment < 0:
        raise ValueError("hosts-per-segment must be >= 0")
    if access_switches_per_segment < 1:
        raise ValueError("access-switches-per-segment must be >= 1")
    if servers < 0:
        raise ValueError("servers must be >= 0")

    pool = ipaddress.ip_network(address_pool, strict=False)
    segment_networks = _subnets(pool, segment_prefix, segments, label="segment-prefix")
    srv_net = ipaddress.ip_network(server_network, strict=False)
    server_gateway = _last_gateway(srv_net)
    server_addresses = _host_list(srv_net, count=servers, skip={server_gateway}) if servers else []
    dns_ip = str(server_addresses[1] if len(server_addresses) > 1 else server_addresses[0]) if server_addresses else ""
    slug = name.upper()

    server_specs: list[dict[str, Any]] = []
    for index, address in enumerate(server_addresses, start=1):
        if index == 1:
            server_name = f"SRV-{slug}-WEB"
            services: dict[str, Any] = {"http": True}
        elif index == 2:
            server_name = f"SRV-{slug}-DNS"
            services = {"dns": {"enabled": True, "records": [{"name": f"www.{name.lower()}.local", "ip": str(server_addresses[0])}]}}
        elif index == 3:
            server_name = f"SRV-{slug}-FTP"
            services = {"ftp": {"enabled": True, "accounts": [{"username": "student", "password": "packet", "permissions": "RWDNL"}]}}
        elif index == 4:
            server_name = f"SRV-{slug}-MAIL"
            services = {"email": {"enabled": True, "domain": f"{name.lower()}.local", "accounts": [{"username": "student", "password": "packet"}]}}
        else:
            server_name = f"SRV-{slug}-{index}"
            services = {"http": True}
        server_specs.append({"name": server_name, "ip": str(address), "services": services})

    segment_specs = []
    for index, network in enumerate(segment_networks, start=1):
        gateway = _last_gateway(network)
        segment_specs.append(
            {
                "name": f"SEG-{index}",
                "vlan": vlan_base + index - 1,
                "subnet": str(network),
                "gateway": str(gateway),
                "dns": dns_ip,
                "representative_hosts": hosts_per_segment,
                "access_switches": access_switches_per_segment,
                "core": f"MLS{((index - 1) % cores) + 1}",
            }
        )

    spec = {
        "name": name,
        "core": {"count": cores, "prefix": "MLS", "interconnect_pool": interconnect_pool, "interconnect_prefix": 30},
        "server_defaults": {"mask": _mask(srv_net), "gateway": str(server_gateway), "dns": dns_ip},
        "server_switch": {"name": f"SW-{slug}-SRV", "vlan": server_vlan, "core": "MLS1"},
        "servers": server_specs,
        "segments": segment_specs,
    }
    plan = compose_campus(spec, do_layout=not no_layout, layout_style=layout_style)
    plan["metadata"] = {"source": "pt730-template campus", "name": name, "address_pool": str(pool), "server_network": str(srv_net)}
    if l3 or routing != "none":
        plan = configured_plan(plan, include_l3=True, routing=routing)
        plan["metadata"]["source"] = "pt730-template campus"
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pt730-template", description=__doc__)
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("schema", help="print built-in template schema")

    lan_p = sub.add_parser("lan-star", help="generate a router-switch-PC/server star LAN")
    lan_p.add_argument("--name", default="LAN")
    lan_p.add_argument("--pcs", type=int, default=2)
    lan_p.add_argument("--servers", type=int, default=0)
    lan_p.add_argument("--network", default="192.168.10.0/24")
    lan_p.add_argument("--gateway")
    lan_p.add_argument("--dns")
    lan_p.add_argument("--layout-style", choices=STYLES, default="lan")
    lan_p.add_argument("--no-layout", action="store_true")
    lan_p.add_argument("--output", type=Path)

    wifi_p = sub.add_parser("wireless-lan", help="generate a router-switch-AP-laptop wireless LAN")
    wifi_p.add_argument("--name", default="WIFI")
    wifi_p.add_argument("--aps", type=int, default=1)
    wifi_p.add_argument("--laptops", type=int, default=3)
    wifi_p.add_argument("--servers", type=int, default=1)
    wifi_p.add_argument("--network", default="192.168.80.0/24")
    wifi_p.add_argument("--gateway")
    wifi_p.add_argument("--dns")
    wifi_p.add_argument("--ssid", default="PT730-LAB")
    wifi_p.add_argument("--layout-style", choices=STYLES, default="lan")
    wifi_p.add_argument("--no-layout", action="store_true")
    wifi_p.add_argument("--output", type=Path)

    roas_p = sub.add_parser("vlan-router-on-stick", help="generate a router-on-a-stick VLAN trunk lab")
    roas_p.add_argument("--name", default="ROAS")
    roas_p.add_argument("--vlans", type=int, default=3)
    roas_p.add_argument("--hosts-per-vlan", type=int, default=2)
    roas_p.add_argument("--servers-per-vlan", type=int, default=0)
    roas_p.add_argument("--address-pool", default="192.168.20.0/22")
    roas_p.add_argument("--vlan-prefix", type=int, default=24)
    roas_p.add_argument("--vlan-base", type=int, default=10)
    roas_p.add_argument("--native-vlan", type=int)
    roas_p.add_argument("--domain", default="roas.local")
    roas_p.add_argument("--layout-style", choices=STYLES, default="hierarchical")
    roas_p.add_argument("--no-layout", action="store_true")
    roas_p.add_argument("--output", type=Path)

    edge_p = sub.add_parser("edge-security", help="generate an ISP edge NAT/ACL/DMZ security lab")
    edge_p.add_argument("--name", default="EDGE")
    edge_p.add_argument("--inside-hosts", type=int, default=3)
    edge_p.add_argument("--dmz-servers", type=int, default=2)
    edge_p.add_argument("--internet-hosts", type=int, default=1)
    edge_p.add_argument("--inside-network", default="192.168.10.0/24")
    edge_p.add_argument("--dmz-network", default="172.16.10.0/24")
    edge_p.add_argument("--wan-network", default="203.0.113.0/30")
    edge_p.add_argument("--internet-network", default="198.51.100.0/24")
    edge_p.add_argument("--domain", default="edge.local")
    edge_p.add_argument("--layout-style", choices=STYLES, default="hierarchical")
    edge_p.add_argument("--no-layout", action="store_true")
    edge_p.add_argument("--output", type=Path)

    ring_p = sub.add_parser("router-ring", help="generate a serial router ring with RIPv2")
    ring_p.add_argument("--name", default="RING")
    ring_p.add_argument("--routers", type=int, default=4)
    ring_p.add_argument("--interconnect-pool", default="10.20.0.0/28")
    ring_p.add_argument("--layout-style", choices=STYLES, default="ring")
    ring_p.add_argument("--no-layout", action="store_true")
    ring_p.add_argument("--output", type=Path)

    wan_p = sub.add_parser("wan-ring", help="generate a serial multi-site WAN ring with access LANs")
    wan_p.add_argument("--name", default="WAN")
    wan_p.add_argument("--sites", type=int, default=3)
    wan_p.add_argument("--hosts-per-site", type=int, default=2)
    wan_p.add_argument("--servers-per-site", type=int, default=1)
    wan_p.add_argument("--interconnect-pool", default="10.30.0.0/28")
    wan_p.add_argument("--lan-pool", default="192.168.100.0/22")
    wan_p.add_argument("--lan-prefix", type=int, default=24)
    wan_p.add_argument("--routing", choices=("none", "rip", "static"), default="rip")
    wan_p.add_argument("--layout-style", choices=STYLES, default="ring")
    wan_p.add_argument("--no-layout", action="store_true")
    wan_p.add_argument("--output", type=Path)

    campus_p = sub.add_parser("campus", help="generate a representative campus topology")
    campus_p.add_argument("--name", default="CAMPUS")
    campus_p.add_argument("--cores", type=int, default=2)
    campus_p.add_argument("--segments", type=int, default=4)
    campus_p.add_argument("--hosts-per-segment", type=int, default=2)
    campus_p.add_argument("--access-switches-per-segment", type=int, default=1)
    campus_p.add_argument("--servers", type=int, default=2)
    campus_p.add_argument("--address-pool", default="192.168.0.0/21")
    campus_p.add_argument("--segment-prefix", type=int, default=24)
    campus_p.add_argument("--server-network", default="172.16.1.0/26")
    campus_p.add_argument("--server-vlan", type=int, default=10)
    campus_p.add_argument("--vlan-base", type=int, default=20)
    campus_p.add_argument("--interconnect-pool", default="10.10.0.0/24")
    campus_p.add_argument("--l3", action="store_true")
    campus_p.add_argument("--routing", choices=("none", "rip", "static"), default="none")
    campus_p.add_argument("--layout-style", choices=STYLES, default="campus")
    campus_p.add_argument("--no-layout", action="store_true")
    campus_p.add_argument("--output", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.cmd == "schema":
            _emit(schema(), None, compact=args.compact)
            return 0
        if args.cmd == "lan-star":
            _emit(
                lan_star(
                    name=args.name,
                    pcs=args.pcs,
                    servers=args.servers,
                    network=args.network,
                    gateway=args.gateway,
                    dns=args.dns,
                    layout_style=args.layout_style,
                    no_layout=args.no_layout,
                ),
                args.output,
                compact=args.compact,
            )
            return 0
        if args.cmd == "wireless-lan":
            _emit(
                wireless_lan(
                    name=args.name,
                    aps=args.aps,
                    laptops=args.laptops,
                    servers=args.servers,
                    network=args.network,
                    gateway=args.gateway,
                    dns=args.dns,
                    ssid=args.ssid,
                    layout_style=args.layout_style,
                    no_layout=args.no_layout,
                ),
                args.output,
                compact=args.compact,
            )
            return 0
        if args.cmd == "vlan-router-on-stick":
            _emit(
                vlan_router_on_stick(
                    name=args.name,
                    vlans=args.vlans,
                    hosts_per_vlan=args.hosts_per_vlan,
                    servers_per_vlan=args.servers_per_vlan,
                    address_pool=args.address_pool,
                    vlan_prefix=args.vlan_prefix,
                    vlan_base=args.vlan_base,
                    native_vlan=args.native_vlan,
                    domain=args.domain,
                    layout_style=args.layout_style,
                    no_layout=args.no_layout,
                ),
                args.output,
                compact=args.compact,
            )
            return 0
        if args.cmd == "edge-security":
            _emit(
                edge_security(
                    name=args.name,
                    inside_hosts=args.inside_hosts,
                    dmz_servers=args.dmz_servers,
                    internet_hosts=args.internet_hosts,
                    inside_network=args.inside_network,
                    dmz_network=args.dmz_network,
                    wan_network=args.wan_network,
                    internet_network=args.internet_network,
                    domain=args.domain,
                    layout_style=args.layout_style,
                    no_layout=args.no_layout,
                ),
                args.output,
                compact=args.compact,
            )
            return 0
        if args.cmd == "router-ring":
            _emit(
                router_ring(
                    name=args.name,
                    routers=args.routers,
                    interconnect_pool=args.interconnect_pool,
                    layout_style=args.layout_style,
                    no_layout=args.no_layout,
                ),
                args.output,
                compact=args.compact,
            )
            return 0
        if args.cmd == "wan-ring":
            _emit(
                wan_ring(
                    name=args.name,
                    sites=args.sites,
                    hosts_per_site=args.hosts_per_site,
                    servers_per_site=args.servers_per_site,
                    interconnect_pool=args.interconnect_pool,
                    lan_pool=args.lan_pool,
                    lan_prefix=args.lan_prefix,
                    routing=args.routing,
                    layout_style=args.layout_style,
                    no_layout=args.no_layout,
                ),
                args.output,
                compact=args.compact,
            )
            return 0
        if args.cmd == "campus":
            _emit(
                campus(
                    name=args.name,
                    cores=args.cores,
                    segments=args.segments,
                    hosts_per_segment=args.hosts_per_segment,
                    access_switches_per_segment=args.access_switches_per_segment,
                    servers=args.servers,
                    address_pool=args.address_pool,
                    segment_prefix=args.segment_prefix,
                    server_network=args.server_network,
                    server_vlan=args.server_vlan,
                    vlan_base=args.vlan_base,
                    interconnect_pool=args.interconnect_pool,
                    layout_style=args.layout_style,
                    no_layout=args.no_layout,
                    l3=args.l3,
                    routing=args.routing,
                ),
                args.output,
                compact=args.compact,
            )
            return 0
        raise ValueError(f"unknown command: {args.cmd}")
    except Exception as exc:  # noqa: BLE001
        print(f"pt730-template: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
