#!/usr/bin/env python3
"""Packet Tracer 7.3.0 Server-PT service CLI over the local bridge."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
from typing import Any

from topology_cli import DEFAULT_BRIDGE, eval_js


def js_string(value: str) -> str:
    return json.dumps(value)


def js_bool(value: bool) -> str:
    return "true" if value else "false"


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def eval_json(js: str, *, bridge: str, timeout: float) -> dict[str, Any]:
    raw = eval_js(js, bridge, timeout)
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"expected JSON object, got {type(parsed).__name__}")
    return parsed


def inspect_js(device: str, port: str) -> str:
    return f"""
var deviceName = {js_string(device)};
var portName = {js_string(port)};
var d = ipc.network().getDevice(deviceName);
if (!d) throw new Error("device not found: " + deviceName);
if (d.getModel && d.getModel() !== "Server-PT") throw new Error(deviceName + " is " + d.getModel() + ", not Server-PT");

function text(block, tag) {{
  var re = new RegExp("<" + tag + ">([\\\\s\\\\S]*?)</" + tag + ">");
  var m = re.exec(block || "");
  return m ? m[1] : "";
}}
function section(xml, tag) {{
  var re = new RegExp("<" + tag + ">[\\\\s\\\\S]*?</" + tag + ">");
  var m = re.exec(xml || "");
  return m ? m[0] : "";
}}
function boolCall(obj, method) {{
  try {{
    if (obj && typeof obj[method] === "function") return !!obj[method]();
  }} catch (e) {{}}
  return null;
}}
function parseDnsRecords(dnsXml) {{
  var records = [];
  var re = /<RESOURCE-RECORD>[\\s\\S]*?<\\/RESOURCE-RECORD>/g;
  var m;
  while ((m = re.exec(dnsXml || "")) !== null) {{
    var block = m[0];
    records.push({{
      type: text(block, "TYPE"),
      name: text(block, "NAME"),
      ttl: text(block, "TTL"),
      ip: text(block, "IPADDRESS")
    }});
  }}
  return records;
}}
function parseFtpAccounts(ftpXml) {{
  var accounts = [];
  var re = /<ACCOUNT>[\\s\\S]*?<\\/ACCOUNT>/g;
  var m;
  while ((m = re.exec(ftpXml || "")) !== null) {{
    var block = m[0];
    accounts.push({{
      username: text(block, "USERNAME"),
      password: text(block, "PASSWORD"),
      permissions: text(block, "PERMISSIONS")
    }});
  }}
  return accounts;
}}
function parseEmailAccounts(raw) {{
  var accounts = [];
  var parts = String(raw || "").split(/[,;\\n]+/);
  for (var i = 0; i < parts.length; i++) {{
    var item = parts[i].replace(/^\\s+|\\s+$/g, "");
    if (!item) continue;
    var colon = item.indexOf(":");
    accounts.push(colon >= 0 ? {{username: item.substring(0, colon), password: item.substring(colon + 1)}} : {{username: item}});
  }}
  return accounts;
}}
function poolInfo(pool) {{
  function val(method) {{
    try {{ return pool && typeof pool[method] === "function" ? String(pool[method]()) : ""; }}
    catch (e) {{ return "ERROR: " + (e && e.message ? e.message : e); }}
  }}
  return {{
    network: val("getNetworkAddress"),
    mask: val("getSubnetMask"),
    start_ip: val("getStartIp"),
    end_ip: val("getEndIp"),
    default_gateway: val("getDefaultRouter"),
    dns_server: val("getDnsServerIp"),
    tftp_address: val("getTftpAddress"),
    max_users: val("getMaxUsers"),
    domain_name: val("getDomainName")
  }};
}}

var port = d.getPort(portName);
var xml = String(d.serializeToXml());
var dns = d.getProcess("DnsServerProcess");
var http = d.getProcess("HttpServerProcess");
var ftp = d.getProcess("FtpServerProcess");
var tftp = d.getProcess("TftpServerProcess") || d.getProcess("TftpServer");
var ntp = d.getProcess("NtpServerProcess");
var syslog = d.getProcess("SyslogServerProcess");
var email = d.getProcess("EmailServerProcess");
var smtp = d.getProcess("SmtpServerProcess");
var pop3 = d.getProcess("Pop3ServerProcess");
var dhcp = d.getProcess("DhcpServerMainProcess").getDhcpServerProcessByPortName(portName);
var emailRaw = "";
try {{ if (email && typeof email.getAllEmailAcctAsStrings === "function") emailRaw = String(email.getAllEmailAcctAsStrings()); }} catch (e) {{}}
var pools = [];
if (dhcp) {{
  try {{
    for (var i = 0; i < dhcp.getPoolCount(); i++) {{
      pools.push(poolInfo(dhcp.getPoolAt(i)));
    }}
  }} catch (e) {{}}
}}
return JSON.stringify({{
  device: deviceName,
  model: d.getModel(),
  port: {{
    name: portName,
    ip: port && port.getIpAddress ? String(port.getIpAddress()) : "",
    mask: port && port.getSubnetMask ? String(port.getSubnetMask()) : "",
  }},
  services: {{
    http: {{enabled: boolCall(http, "isEnabled")}},
    ftp: {{enabled: boolCall(ftp, "isEnabled"), accounts: parseFtpAccounts(section(xml, "FTP_SERVER"))}},
    tftp: {{enabled: boolCall(tftp, "isEnabled")}},
    dns: {{
      enabled: boolCall(dns, "isEnabled"),
      records: parseDnsRecords(section(xml, "DNS_SERVER"))
    }},
    email: {{
      smtp_enabled: boolCall(smtp, "isEnabled"),
      pop3_enabled: boolCall(pop3, "isEnabled"),
      domain: smtp && smtp.getServerDomainName ? String(smtp.getServerDomainName()) : "",
      accounts_raw: emailRaw,
      accounts: parseEmailAccounts(emailRaw)
    }},
    ntp: {{
      enabled: boolCall(ntp, "isEnabled"),
      authentication: boolCall(ntp, "getNtpServerAuthentication"),
      key_id: ntp && ntp.getKeyId ? String(ntp.getKeyId()) : "",
      md5: ntp && ntp.getServerMd5Str ? String(ntp.getServerMd5Str()) : ""
    }},
    syslog: {{
      enabled: boolCall(syslog, "isEnabled"),
      port: syslog && syslog.getPortNumber ? String(syslog.getPortNumber()) : ""
    }},
    dhcp: {{
      enabled: boolCall(dhcp, "isEnable"),
      pool_count: dhcp ? dhcp.getPoolCount() : 0,
      pools: pools
    }}
  }},
  xml_sections: {{
    http: section(xml, "HTTP_SERVER"),
    ftp: section(xml, "FTP_SERVER"),
    tftp: section(xml, "TFTP_SERVER"),
    dns: section(xml, "DNS_SERVER"),
    email: section(xml, "EMAIL_SERVER"),
    ntp: section(xml, "NTP_SERVER"),
    syslog: section(xml, "SYSLOG_SERVER"),
    dhcp: section(xml, "DHCP_SERVERS")
  }}
}});
"""


def service_enable_js(device: str, service: str, enabled: bool) -> str:
    process_by_service = {
        "http": ("HttpServerProcess", "setEnable", "isEnabled"),
        "dns": ("DnsServerProcess", "setEnable", "isEnabled"),
        "ftp": ("FtpServerProcess", "setEnabled", "isEnabled"),
        "tftp": ("TftpServerProcess", "setEnabled", "isEnabled"),
        "ntp": ("NtpServerProcess", "setEnabled", "isEnabled"),
        "syslog": ("SyslogServerProcess", "setEnable", "isEnabled"),
        "smtp": ("SmtpServerProcess", "setEnable", "isEnabled"),
        "pop3": ("Pop3ServerProcess", "setEnable", "isEnabled"),
    }
    process, setter, getter = process_by_service[service]
    return f"""
var deviceName = {js_string(device)};
var d = ipc.network().getDevice(deviceName);
if (!d) throw new Error("device not found: " + deviceName);
var p = d.getProcess({js_string(process)});
if (!p || typeof p.{setter} !== "function") throw new Error("{service} process is not writable on " + deviceName);
p.{setter}({js_bool(enabled)});
return JSON.stringify({{device: deviceName, service: {js_string(service)}, enabled: !!p.{getter}()}});
"""


def email_enable_js(device: str, enabled: bool, domain: str | None) -> str:
    return f"""
var deviceName = {js_string(device)};
var d = ipc.network().getDevice(deviceName);
if (!d) throw new Error("device not found: " + deviceName);
var smtp = d.getProcess("SmtpServerProcess");
var pop3 = d.getProcess("Pop3ServerProcess");
if (!smtp || typeof smtp.setEnable !== "function") throw new Error("SMTP process is not writable on " + deviceName);
if (!pop3 || typeof pop3.setEnable !== "function") throw new Error("POP3 process is not writable on " + deviceName);
smtp.setEnable({js_bool(enabled)});
pop3.setEnable({js_bool(enabled)});
if ({json.dumps(domain)} !== null) {{
  if (typeof smtp.setServerDomainName !== "function") throw new Error("SMTP domain API is unavailable on " + deviceName);
  smtp.setServerDomainName({json.dumps(domain)});
}}
return JSON.stringify({{
  device: deviceName,
  service: "email",
  smtp_enabled: !!smtp.isEnabled(),
  pop3_enabled: !!pop3.isEnabled(),
  domain: smtp.getServerDomainName ? String(smtp.getServerDomainName()) : ""
}});
"""


def email_add_js(device: str, username: str, password: str, enable: bool, domain: str | None) -> str:
    return f"""
var deviceName = {js_string(device)};
var d = ipc.network().getDevice(deviceName);
if (!d) throw new Error("device not found: " + deviceName);
var email = d.getProcess("EmailServerProcess");
var smtp = d.getProcess("SmtpServerProcess");
var pop3 = d.getProcess("Pop3ServerProcess");
if (!email || typeof email.addUser !== "function") throw new Error("Email user API is unavailable on " + deviceName);
if ({js_bool(enable)}) {{
  if (smtp && typeof smtp.setEnable === "function") smtp.setEnable(true);
  if (pop3 && typeof pop3.setEnable === "function") pop3.setEnable(true);
}}
if ({json.dumps(domain)} !== null && smtp && typeof smtp.setServerDomainName === "function") smtp.setServerDomainName({json.dumps(domain)});
try {{ if (typeof email.deleteUser === "function") email.deleteUser({js_string(username)}); }} catch (e) {{}}
var added = !!email.addUser({js_string(username)}, {js_string(password)});
var accounts = email.getAllEmailAcctAsStrings ? String(email.getAllEmailAcctAsStrings()) : "";
return JSON.stringify({{
  device: deviceName,
  service: "email",
  username: {js_string(username)},
  added: added,
  smtp_enabled: smtp && smtp.isEnabled ? !!smtp.isEnabled() : null,
  pop3_enabled: pop3 && pop3.isEnabled ? !!pop3.isEnabled() : null,
  domain: smtp && smtp.getServerDomainName ? String(smtp.getServerDomainName()) : "",
  accounts_raw: accounts
}});
"""


def email_remove_js(device: str, username: str) -> str:
    return f"""
var deviceName = {js_string(device)};
var d = ipc.network().getDevice(deviceName);
if (!d) throw new Error("device not found: " + deviceName);
var email = d.getProcess("EmailServerProcess");
if (!email || typeof email.deleteUser !== "function") throw new Error("Email delete API is unavailable on " + deviceName);
var removed = !!email.deleteUser({js_string(username)});
var accounts = email.getAllEmailAcctAsStrings ? String(email.getAllEmailAcctAsStrings()) : "";
return JSON.stringify({{device: deviceName, service: "email", removed: {js_string(username)}, ok: removed, accounts_raw: accounts}});
"""


def ntp_config_js(device: str, enabled: bool | None, auth: bool | None, key_id: str | None, md5: str | None) -> str:
    return f"""
var deviceName = {js_string(device)};
var d = ipc.network().getDevice(deviceName);
if (!d) throw new Error("device not found: " + deviceName);
var ntp = d.getProcess("NtpServerProcess");
if (!ntp) throw new Error("NTP process is unavailable on " + deviceName);
if ({json.dumps(enabled)} !== null) ntp.setEnabled({json.dumps(enabled)});
if ({json.dumps(auth)} !== null) ntp.setNtpServerAuthentication({json.dumps(auth)});
if ({json.dumps(key_id)} !== null) ntp.setKeyID({json.dumps(key_id)});
if ({json.dumps(md5)} !== null) ntp.setServerMd5Str({json.dumps(md5)});
return JSON.stringify({{
  device: deviceName,
  service: "ntp",
  enabled: ntp.isEnabled ? !!ntp.isEnabled() : null,
  authentication: ntp.getNtpServerAuthentication ? !!ntp.getNtpServerAuthentication() : null,
  key_id: ntp.getKeyId ? String(ntp.getKeyId()) : "",
  md5: ntp.getServerMd5Str ? String(ntp.getServerMd5Str()) : ""
}});
"""


def syslog_config_js(device: str, enabled: bool | None, port: int | None) -> str:
    return f"""
var deviceName = {js_string(device)};
var d = ipc.network().getDevice(deviceName);
if (!d) throw new Error("device not found: " + deviceName);
var syslog = d.getProcess("SyslogServerProcess");
if (!syslog) throw new Error("Syslog process is unavailable on " + deviceName);
if ({json.dumps(enabled)} !== null) syslog.setEnable({json.dumps(enabled)});
if ({json.dumps(port)} !== null) syslog.setPortNumber(Number({json.dumps(port)}));
return JSON.stringify({{
  device: deviceName,
  service: "syslog",
  enabled: syslog.isEnabled ? !!syslog.isEnabled() : null,
  port: syslog.getPortNumber ? String(syslog.getPortNumber()) : ""
}});
"""


def dhcp_enable_js(device: str, port: str, enabled: bool) -> str:
    return f"""
var deviceName = {js_string(device)};
var portName = {js_string(port)};
var d = ipc.network().getDevice(deviceName);
if (!d) throw new Error("device not found: " + deviceName);
var p = d.getProcess("DhcpServerMainProcess").getDhcpServerProcessByPortName(portName);
if (!p || typeof p.setEnable !== "function") throw new Error("DHCP process is not writable on " + deviceName + ":" + portName);
p.setEnable({js_bool(enabled)});
return JSON.stringify({{device: deviceName, port: portName, service: "dhcp", enabled: !!p.isEnable()}});
"""


def dns_add_js(device: str, hostname: str, ip: str, enable: bool) -> str:
    return f"""
var deviceName = {js_string(device)};
var d = ipc.network().getDevice(deviceName);
if (!d) throw new Error("device not found: " + deviceName);
var p = d.getProcess("DnsServerProcess");
if (!p || typeof p.addARecordToNameServerDb !== "function") throw new Error("DNS process is not writable on " + deviceName);
if ({js_bool(enable)} && typeof p.setEnable === "function") p.setEnable(true);
var ret = p.addARecordToNameServerDb({js_string(hostname)}, {js_string(ip)});
return JSON.stringify({{device: deviceName, service: "dns", record: {{type: "A-REC", name: {js_string(hostname)}, ip: {js_string(ip)}}}, enabled: !!p.isEnabled(), added: !!ret}});
"""


def ftp_add_js(device: str, username: str, password: str, permissions: str, enable: bool) -> str:
    return f"""
var deviceName = {js_string(device)};
var d = ipc.network().getDevice(deviceName);
if (!d) throw new Error("device not found: " + deviceName);
var ftp = d.getProcess("FtpServerProcess");
if (!ftp || typeof ftp.getFtpUserAccountManager !== "function") throw new Error("FTP user manager is unavailable on " + deviceName);
if ({js_bool(enable)} && typeof ftp.setEnabled === "function") ftp.setEnabled(true);
var mgr = ftp.getFtpUserAccountManager();
if (!mgr || typeof mgr.addFtpUser !== "function") throw new Error("FTP add user API is unavailable on " + deviceName);
if (mgr.isExistingUser && mgr.isExistingUser({js_string(username)})) mgr.removeFtpUser({js_string(username)});
mgr.addFtpUser({js_string(username)}, {js_string(password)}, {js_string(permissions)});
return JSON.stringify({{device: deviceName, service: "ftp", enabled: !!ftp.isEnabled(), username: {js_string(username)}, permissions: {js_string(permissions)}, user_count: String(mgr.getUsersCount())}});
"""


def ftp_remove_js(device: str, username: str) -> str:
    return f"""
var deviceName = {js_string(device)};
var d = ipc.network().getDevice(deviceName);
if (!d) throw new Error("device not found: " + deviceName);
var ftp = d.getProcess("FtpServerProcess");
if (!ftp || typeof ftp.getFtpUserAccountManager !== "function") throw new Error("FTP user manager is unavailable on " + deviceName);
var mgr = ftp.getFtpUserAccountManager();
var existed = mgr.isExistingUser ? !!mgr.isExistingUser({js_string(username)}) : null;
if (existed && typeof mgr.removeFtpUser === "function") mgr.removeFtpUser({js_string(username)});
return JSON.stringify({{device: deviceName, service: "ftp", removed: {js_string(username)}, existed: existed, user_count: String(mgr.getUsersCount())}});
"""


def dhcp_config_js(args: argparse.Namespace) -> str:
    fields = {
        "network": args.network,
        "mask": args.mask,
        "start_ip": args.start,
        "end_ip": args.end,
        "default_gateway": args.gateway,
        "dns_server": args.dns,
        "max_users": args.max_users,
    }
    fields_json = json.dumps(fields)
    return f"""
var deviceName = {js_string(args.device)};
var portName = {js_string(args.port)};
var poolIndex = {int(args.pool_index)};
var fields = {fields_json};
var d = ipc.network().getDevice(deviceName);
if (!d) throw new Error("device not found: " + deviceName);
var dhcp = d.getProcess("DhcpServerMainProcess").getDhcpServerProcessByPortName(portName);
if (!dhcp) throw new Error("DHCP process not found on " + deviceName + ":" + portName);
var pool = dhcp.getPoolAt(poolIndex);
if (!pool) throw new Error("DHCP pool index not found: " + poolIndex);
if ({js_bool(args.enable)}) dhcp.setEnable(true);
if (fields.network) pool.setNetworkAddress(fields.network);
if (fields.mask) {{
  var networkForMask = fields.network || pool.getNetworkAddress();
  pool.setNetworkMask(networkForMask, fields.mask);
}}
if (fields.default_gateway) pool.setDefaultRouter(fields.default_gateway);
if (fields.dns_server) pool.setDnsServerIp(fields.dns_server);
if (fields.start_ip) {{
  pool.setStartIp(fields.start_ip);
  if (typeof pool.setNextAvailableIpAddress === "function") pool.setNextAvailableIpAddress(fields.start_ip);
}}
if (fields.end_ip) pool.setEndIp(fields.end_ip);
if (fields.max_users !== null && fields.max_users !== undefined) pool.setMaxUsers(Number(fields.max_users));
return JSON.stringify({{
  device: deviceName,
  port: portName,
  service: "dhcp",
  enabled: !!dhcp.isEnable(),
  pool_index: poolIndex,
  pool: {{
    network: String(pool.getNetworkAddress()),
    mask: String(pool.getSubnetMask()),
    start_ip: String(pool.getStartIp()),
    end_ip: String(pool.getEndIp()),
    default_gateway: String(pool.getDefaultRouter()),
    dns_server: String(pool.getDnsServerIp()),
    max_users: String(pool.getMaxUsers())
  }}
}});
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge", default=DEFAULT_BRIDGE)
    parser.add_argument("--timeout", type=float, default=15.0)
    sub = parser.add_subparsers(dest="cmd", required=True)

    inspect_p = sub.add_parser("inspect", help="inspect Server-PT service state")
    inspect_p.add_argument("device")
    inspect_p.add_argument("--port", default="FastEthernet0")

    for service in ("http", "dns", "ftp", "tftp", "ntp", "syslog", "smtp", "pop3"):
        p = sub.add_parser(service, help=f"enable or disable {service.upper()} service")
        p.add_argument("device")
        group = p.add_mutually_exclusive_group(required=True)
        group.add_argument("--enable", action="store_true")
        group.add_argument("--disable", action="store_true")

    email_p = sub.add_parser("email", help="enable or disable both SMTP and POP3")
    email_p.add_argument("device")
    email_group = email_p.add_mutually_exclusive_group(required=True)
    email_group.add_argument("--enable", action="store_true")
    email_group.add_argument("--disable", action="store_true")
    email_p.add_argument("--domain", help="SMTP server domain name")

    email_add_p = sub.add_parser("email-add", help="add or replace a Server-PT email user")
    email_add_p.add_argument("device")
    email_add_p.add_argument("username")
    email_add_p.add_argument("password")
    email_add_p.add_argument("--domain", help="SMTP server domain name")
    email_add_p.add_argument("--no-enable", action="store_true", help="do not enable SMTP/POP3 automatically")

    email_rm_p = sub.add_parser("email-remove", help="remove a Server-PT email user")
    email_rm_p.add_argument("device")
    email_rm_p.add_argument("username")

    ntp_cfg_p = sub.add_parser("ntp-config", help="configure NTP authentication fields")
    ntp_cfg_p.add_argument("device")
    ntp_cfg_p.add_argument("--enable", action="store_true")
    ntp_cfg_p.add_argument("--disable", action="store_true")
    ntp_cfg_p.add_argument("--auth", choices=["on", "off"])
    ntp_cfg_p.add_argument("--key-id")
    ntp_cfg_p.add_argument("--md5")

    syslog_cfg_p = sub.add_parser("syslog-config", help="configure Syslog service state and UDP port")
    syslog_cfg_p.add_argument("device")
    syslog_cfg_p.add_argument("--enable", action="store_true")
    syslog_cfg_p.add_argument("--disable", action="store_true")
    syslog_cfg_p.add_argument("--port", type=int)

    dhcp_p = sub.add_parser("dhcp", help="enable or disable DHCP service")
    dhcp_p.add_argument("device")
    dhcp_p.add_argument("--port", default="FastEthernet0")
    dhcp_group = dhcp_p.add_mutually_exclusive_group(required=True)
    dhcp_group.add_argument("--enable", action="store_true")
    dhcp_group.add_argument("--disable", action="store_true")

    dns_add_p = sub.add_parser("dns-add", help="add an A record to Server-PT DNS")
    dns_add_p.add_argument("device")
    dns_add_p.add_argument("hostname")
    dns_add_p.add_argument("ip")
    dns_add_p.add_argument("--no-enable", action="store_true", help="do not enable DNS automatically")

    ftp_add_p = sub.add_parser("ftp-add", help="add or replace a Server-PT FTP user")
    ftp_add_p.add_argument("device")
    ftp_add_p.add_argument("username")
    ftp_add_p.add_argument("password")
    ftp_add_p.add_argument("--permissions", default="RWDNL", help="Packet Tracer FTP permissions string, default RWDNL")
    ftp_add_p.add_argument("--no-enable", action="store_true", help="do not enable FTP automatically")

    ftp_rm_p = sub.add_parser("ftp-remove", help="remove a Server-PT FTP user")
    ftp_rm_p.add_argument("device")
    ftp_rm_p.add_argument("username")

    dhcp_cfg_p = sub.add_parser("dhcp-config", help="configure the default Server-PT DHCP pool")
    dhcp_cfg_p.add_argument("device")
    dhcp_cfg_p.add_argument("--port", default="FastEthernet0")
    dhcp_cfg_p.add_argument("--pool-index", type=int, default=0)
    dhcp_cfg_p.add_argument("--network")
    dhcp_cfg_p.add_argument("--mask")
    dhcp_cfg_p.add_argument("--start")
    dhcp_cfg_p.add_argument("--end")
    dhcp_cfg_p.add_argument("--gateway")
    dhcp_cfg_p.add_argument("--dns")
    dhcp_cfg_p.add_argument("--max-users", type=int)
    dhcp_cfg_p.add_argument("--enable", action="store_true", help="enable DHCP after applying pool settings")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "inspect":
            print_json(eval_json(inspect_js(args.device, args.port), bridge=args.bridge, timeout=args.timeout))
            return 0
        if args.cmd in {"http", "dns", "ftp", "tftp", "ntp", "syslog", "smtp", "pop3"}:
            print_json(eval_json(service_enable_js(args.device, args.cmd, args.enable), bridge=args.bridge, timeout=args.timeout))
            return 0
        if args.cmd == "email":
            print_json(eval_json(email_enable_js(args.device, args.enable, args.domain), bridge=args.bridge, timeout=args.timeout))
            return 0
        if args.cmd == "email-add":
            print_json(eval_json(email_add_js(args.device, args.username, args.password, not args.no_enable, args.domain), bridge=args.bridge, timeout=args.timeout))
            return 0
        if args.cmd == "email-remove":
            print_json(eval_json(email_remove_js(args.device, args.username), bridge=args.bridge, timeout=args.timeout))
            return 0
        if args.cmd == "ntp-config":
            if args.enable and args.disable:
                raise ValueError("--enable and --disable are mutually exclusive")
            enabled = True if args.enable else False if args.disable else None
            auth = True if args.auth == "on" else False if args.auth == "off" else None
            print_json(eval_json(ntp_config_js(args.device, enabled, auth, args.key_id, args.md5), bridge=args.bridge, timeout=args.timeout))
            return 0
        if args.cmd == "syslog-config":
            if args.enable and args.disable:
                raise ValueError("--enable and --disable are mutually exclusive")
            enabled = True if args.enable else False if args.disable else None
            print_json(eval_json(syslog_config_js(args.device, enabled, args.port), bridge=args.bridge, timeout=args.timeout))
            return 0
        if args.cmd == "dhcp":
            print_json(eval_json(dhcp_enable_js(args.device, args.port, args.enable), bridge=args.bridge, timeout=args.timeout))
            return 0
        if args.cmd == "dns-add":
            print_json(eval_json(dns_add_js(args.device, args.hostname, args.ip, not args.no_enable), bridge=args.bridge, timeout=args.timeout))
            return 0
        if args.cmd == "ftp-add":
            print_json(eval_json(ftp_add_js(args.device, args.username, args.password, args.permissions, not args.no_enable), bridge=args.bridge, timeout=args.timeout))
            return 0
        if args.cmd == "ftp-remove":
            print_json(eval_json(ftp_remove_js(args.device, args.username), bridge=args.bridge, timeout=args.timeout))
            return 0
        if args.cmd == "dhcp-config":
            print_json(eval_json(dhcp_config_js(args), bridge=args.bridge, timeout=args.timeout))
            return 0
    except (OSError, ValueError, RuntimeError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"pt730-server: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
