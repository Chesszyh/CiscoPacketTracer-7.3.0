# Packet Tracer Topology Plan

## Devices

| Name | Model | Category | X | Y |
| --- | --- | --- | --- | --- |
| MLS1 | 2960-24TT | switch | 420 | 230 |
| MLS2 | 2960-24TT | switch | 760 | 380 |
| MLS3 | 2960-24TT | switch | 760 | 720 |
| MLS4 | 2960-24TT | switch | 420 | 890 |
| MLS5 | 2960-24TT | switch | 300 | 760 |
| MLS6 | 2960-24TT | switch | 300 | 430 |
| SW-SRV | 2960-24TT | switch | 420 | 70 |
| WEB-SRV | Server-PT | server | 310 | 0 |
| DNS-SRV | Server-PT | server | 420 | 0 |
| DB-SRV | Server-PT | server | 530 | 0 |
| SW-OFFICE | 2960-24TT | switch | 650 | 115 |
| PC-OFFICE-1 | PC-PT | pc | 605 | 235 |
| PC-OFFICE-2 | PC-PT | pc | 700 | 235 |
| SW-TEACH | 2960-24TT | switch | 985 | 300 |
| PC-TEACHING-1 | PC-PT | pc | 940 | 420 |
| PC-TEACHING-2 | PC-PT | pc | 1035 | 420 |
| SW-RESEARCH | 2960-24TT | switch | 985 | 500 |
| PC-RESEARCH-1 | PC-PT | pc | 940 | 620 |
| PC-RESEARCH-2 | PC-PT | pc | 1035 | 620 |
| SW-GRAD | 2960-24TT | switch | 985 | 780 |
| PC-GRADUATE-1 | PC-PT | pc | 940 | 900 |
| PC-GRADUATE-2 | PC-PT | pc | 1035 | 900 |
| SW-LAB-A | 2960-24TT | switch | 650 | 1040 |
| PC-LABA-1 | PC-PT | pc | 605 | 1160 |
| PC-LABA-2 | PC-PT | pc | 700 | 1160 |
| SW-LAB-B | 2960-24TT | switch | 420 | 1080 |
| PC-LABB-1 | PC-PT | pc | 375 | 1200 |
| PC-LABB-2 | PC-PT | pc | 470 | 1200 |
| SW-LAB-C | 2960-24TT | switch | 140 | 940 |
| PC-LABC-1 | PC-PT | pc | 95 | 1060 |
| PC-LABC-2 | PC-PT | pc | 205 | 1060 |
| SW-LAB-D | 2960-24TT | switch | 140 | 680 |
| PC-LABD-1 | PC-PT | pc | 95 | 800 |
| PC-LABD-2 | PC-PT | pc | 205 | 800 |
| SW-LAB-E | 2960-24TT | switch | 140 | 420 |
| PC-LABE-1 | PC-PT | pc | 95 | 540 |
| PC-LABE-2 | PC-PT | pc | 205 | 540 |
| SW-LAB-F | 2960-24TT | switch | 140 | 160 |
| PC-LABF-1 | PC-PT | pc | 95 | 280 |
| PC-LABF-2 | PC-PT | pc | 205 | 280 |

## Links

| A | Port A | B | Port B | Cable | VLAN | Note |
| --- | --- | --- | --- | --- | --- | --- |
| MLS1 | GigabitEthernet0/1 | MLS2 | GigabitEthernet0/1 | cross |  | 10.10.12.0/30 |
| MLS2 | GigabitEthernet0/2 | MLS3 | GigabitEthernet0/1 | cross |  | 10.10.23.0/30 |
| MLS3 | GigabitEthernet0/2 | MLS4 | GigabitEthernet0/1 | cross |  | 10.10.34.0/30 |
| MLS4 | GigabitEthernet0/2 | MLS5 | GigabitEthernet0/1 | cross |  | 10.10.45.0/30 |
| MLS5 | GigabitEthernet0/2 | MLS6 | GigabitEthernet0/1 | cross |  | 10.10.56.0/30 |
| MLS6 | GigabitEthernet0/2 | MLS1 | GigabitEthernet0/2 | cross |  | 10.10.61.0/30 |
| MLS1 | FastEthernet0/1 | SW-SRV | GigabitEthernet0/1 | cross | 10 |  |
| SW-SRV | FastEthernet0/1 | WEB-SRV | FastEthernet0 | straight | 10 |  |
| SW-SRV | FastEthernet0/2 | DNS-SRV | FastEthernet0 | straight | 10 |  |
| SW-SRV | FastEthernet0/3 | DB-SRV | FastEthernet0 | straight | 10 |  |
| MLS1 | FastEthernet0/2 | SW-OFFICE | GigabitEthernet0/1 | cross | 20 |  |
| SW-OFFICE | FastEthernet0/1 | PC-OFFICE-1 | FastEthernet0 | straight | 20 |  |
| SW-OFFICE | FastEthernet0/2 | PC-OFFICE-2 | FastEthernet0 | straight | 20 |  |
| MLS2 | FastEthernet0/1 | SW-TEACH | GigabitEthernet0/1 | cross | 30 |  |
| SW-TEACH | FastEthernet0/1 | PC-TEACHING-1 | FastEthernet0 | straight | 30 |  |
| SW-TEACH | FastEthernet0/2 | PC-TEACHING-2 | FastEthernet0 | straight | 30 |  |
| MLS2 | FastEthernet0/2 | SW-RESEARCH | GigabitEthernet0/1 | cross | 40 |  |
| SW-RESEARCH | FastEthernet0/1 | PC-RESEARCH-1 | FastEthernet0 | straight | 40 |  |
| SW-RESEARCH | FastEthernet0/2 | PC-RESEARCH-2 | FastEthernet0 | straight | 40 |  |
| MLS3 | FastEthernet0/1 | SW-GRAD | GigabitEthernet0/1 | cross | 50 |  |
| SW-GRAD | FastEthernet0/1 | PC-GRADUATE-1 | FastEthernet0 | straight | 50 |  |
| SW-GRAD | FastEthernet0/2 | PC-GRADUATE-2 | FastEthernet0 | straight | 50 |  |
| MLS4 | FastEthernet0/1 | SW-LAB-A | GigabitEthernet0/1 | cross | 60 |  |
| SW-LAB-A | FastEthernet0/1 | PC-LABA-1 | FastEthernet0 | straight | 60 |  |
| SW-LAB-A | FastEthernet0/2 | PC-LABA-2 | FastEthernet0 | straight | 60 |  |
| MLS4 | FastEthernet0/2 | SW-LAB-B | GigabitEthernet0/1 | cross | 61 |  |
| SW-LAB-B | FastEthernet0/1 | PC-LABB-1 | FastEthernet0 | straight | 61 |  |
| SW-LAB-B | FastEthernet0/2 | PC-LABB-2 | FastEthernet0 | straight | 61 |  |
| MLS5 | FastEthernet0/1 | SW-LAB-C | GigabitEthernet0/1 | cross | 62 |  |
| SW-LAB-C | FastEthernet0/1 | PC-LABC-1 | FastEthernet0 | straight | 62 |  |
| SW-LAB-C | FastEthernet0/2 | PC-LABC-2 | FastEthernet0 | straight | 62 |  |
| MLS5 | FastEthernet0/2 | SW-LAB-D | GigabitEthernet0/1 | cross | 63 |  |
| SW-LAB-D | FastEthernet0/1 | PC-LABD-1 | FastEthernet0 | straight | 63 |  |
| SW-LAB-D | FastEthernet0/2 | PC-LABD-2 | FastEthernet0 | straight | 63 |  |
| MLS6 | FastEthernet0/1 | SW-LAB-E | GigabitEthernet0/1 | cross | 64 |  |
| SW-LAB-E | FastEthernet0/1 | PC-LABE-1 | FastEthernet0 | straight | 64 |  |
| SW-LAB-E | FastEthernet0/2 | PC-LABE-2 | FastEthernet0 | straight | 64 |  |
| MLS6 | FastEthernet0/2 | SW-LAB-F | GigabitEthernet0/1 | cross | 65 |  |
| SW-LAB-F | FastEthernet0/1 | PC-LABF-1 | FastEthernet0 | straight | 65 |  |
| SW-LAB-F | FastEthernet0/2 | PC-LABF-2 | FastEthernet0 | straight | 65 |  |

## PC And Host IP Configs

| Name | Port | DHCP | IP | Mask | Gateway | DNS |
| --- | --- | --- | --- | --- | --- | --- |
| WEB-SRV | FastEthernet0 |  | 172.16.1.10 | 255.255.255.192 | 172.16.1.62 | 172.16.1.11 |
| DNS-SRV | FastEthernet0 |  | 172.16.1.11 | 255.255.255.192 | 172.16.1.62 | 172.16.1.11 |
| DB-SRV | FastEthernet0 |  | 172.16.1.12 | 255.255.255.192 | 172.16.1.62 | 172.16.1.11 |
| PC-OFFICE-1 | FastEthernet0 |  | 192.168.0.1 | 255.255.255.192 | 192.168.0.62 | 172.16.1.11 |
| PC-OFFICE-2 | FastEthernet0 |  | 192.168.0.2 | 255.255.255.192 | 192.168.0.62 | 172.16.1.11 |
| PC-TEACHING-1 | FastEthernet0 |  | 192.168.0.65 | 255.255.255.192 | 192.168.0.126 | 172.16.1.11 |
| PC-TEACHING-2 | FastEthernet0 |  | 192.168.0.66 | 255.255.255.192 | 192.168.0.126 | 172.16.1.11 |
| PC-RESEARCH-1 | FastEthernet0 |  | 192.168.0.129 | 255.255.255.128 | 192.168.0.254 | 172.16.1.11 |
| PC-RESEARCH-2 | FastEthernet0 |  | 192.168.0.130 | 255.255.255.128 | 192.168.0.254 | 172.16.1.11 |
| PC-GRADUATE-1 | FastEthernet0 |  | 192.168.1.1 | 255.255.255.0 | 192.168.1.254 | 172.16.1.11 |
| PC-GRADUATE-2 | FastEthernet0 |  | 192.168.1.2 | 255.255.255.0 | 192.168.1.254 | 172.16.1.11 |
| PC-LABA-1 | FastEthernet0 |  | 192.168.2.1 | 255.255.255.0 | 192.168.2.254 | 172.16.1.11 |
| PC-LABA-2 | FastEthernet0 |  | 192.168.2.2 | 255.255.255.0 | 192.168.2.254 | 172.16.1.11 |
| PC-LABB-1 | FastEthernet0 |  | 192.168.3.1 | 255.255.255.0 | 192.168.3.254 | 172.16.1.11 |
| PC-LABB-2 | FastEthernet0 |  | 192.168.3.2 | 255.255.255.0 | 192.168.3.254 | 172.16.1.11 |
| PC-LABC-1 | FastEthernet0 |  | 192.168.4.1 | 255.255.255.0 | 192.168.4.254 | 172.16.1.11 |
| PC-LABC-2 | FastEthernet0 |  | 192.168.4.2 | 255.255.255.0 | 192.168.4.254 | 172.16.1.11 |
| PC-LABD-1 | FastEthernet0 |  | 192.168.5.1 | 255.255.255.0 | 192.168.5.254 | 172.16.1.11 |
| PC-LABD-2 | FastEthernet0 |  | 192.168.5.2 | 255.255.255.0 | 192.168.5.254 | 172.16.1.11 |
| PC-LABE-1 | FastEthernet0 |  | 192.168.6.1 | 255.255.255.0 | 192.168.6.254 | 172.16.1.11 |
| PC-LABE-2 | FastEthernet0 |  | 192.168.6.2 | 255.255.255.0 | 192.168.6.254 | 172.16.1.11 |
| PC-LABF-1 | FastEthernet0 |  | 192.168.7.1 | 255.255.255.0 | 192.168.7.254 | 172.16.1.11 |
| PC-LABF-2 | FastEthernet0 |  | 192.168.7.2 | 255.255.255.0 | 192.168.7.254 | 172.16.1.11 |

## Address Summary

| Network | Gateway | DNS | Configured Hosts | Sample Hosts |
| --- | --- | --- | --- | --- |
| 172.16.1.0/26 | 172.16.1.62 | 172.16.1.11 | 3 | WEB-SRV, DNS-SRV, DB-SRV |
| 192.168.0.0/26 | 192.168.0.62 | 172.16.1.11 | 2 | PC-OFFICE-1, PC-OFFICE-2 |
| 192.168.0.64/26 | 192.168.0.126 | 172.16.1.11 | 2 | PC-TEACHING-1, PC-TEACHING-2 |
| 192.168.0.128/25 | 192.168.0.254 | 172.16.1.11 | 2 | PC-RESEARCH-1, PC-RESEARCH-2 |
| 192.168.1.0/24 | 192.168.1.254 | 172.16.1.11 | 2 | PC-GRADUATE-1, PC-GRADUATE-2 |
| 192.168.2.0/24 | 192.168.2.254 | 172.16.1.11 | 2 | PC-LABA-1, PC-LABA-2 |
| 192.168.3.0/24 | 192.168.3.254 | 172.16.1.11 | 2 | PC-LABB-1, PC-LABB-2 |
| 192.168.4.0/24 | 192.168.4.254 | 172.16.1.11 | 2 | PC-LABC-1, PC-LABC-2 |
| 192.168.5.0/24 | 192.168.5.254 | 172.16.1.11 | 2 | PC-LABD-1, PC-LABD-2 |
| 192.168.6.0/24 | 192.168.6.254 | 172.16.1.11 | 2 | PC-LABE-1, PC-LABE-2 |
| 192.168.7.0/24 | 192.168.7.254 | 172.16.1.11 | 2 | PC-LABF-1, PC-LABF-2 |
