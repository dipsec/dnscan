#!/usr/bin/env python
#
# dnscan copyright (C) 2013-2014 rbsec
# Licensed under GPLv3, see LICENSE for details
#
from __future__ import print_function

import os
import re
import sys
import threading
import time

try:    # Ugly hack because Python3 decided to rename Queue to queue
    import Queue
except ImportError:
    import queue as Queue

try:
    import argparse
except:
    print("FATAL: Module argparse missing (python-argparse)")
    sys.exit(1)

try:
    import dns.query
    import dns.resolver
    import dns.zone
except:
    print("FATAL: Module dnspython missing (python-dnspython)")
    sys.exit(1)

# Usage: dnscan.py -d <domain name>

class scanner(threading.Thread):
    def __init__(self, queue):
        global wildcard
        threading.Thread.__init__(self)
        self.queue = queue

    def get_name(self, domain):
            global wildcard
            try:
                if sys.stdout.isatty():     # Don't spam output if redirected
                    sys.stdout.write(domain + "                              \r")
                    sys.stdout.flush()
                res = lookup(domain, recordtype)
                if args.tld and res:
                    nameservers = sorted(list(res))
                    ns0 = str(nameservers[0])[:-1]  # First nameserver
                    print(domain + " - " + col.brown + ns0 + col.end)
                if args.tld:
                    if res:
                        print(domain + " - " + res)
                    return
                for rdata in res:
                    if wildcard:
                        if rdata.address == wildcard:
                            return
                    if args.domain_first:
                        print(domain + " - " + col.brown + rdata.address + col.end)
                    else:
                        print(rdata.address + " - " + col.brown + domain + col.end)
                    if outfile:
                        if args.domain_first:
                            print(domain + " - " + rdata.address, file=outfile)
                        else:
                            print(rdata.address + " - " + domain, file=outfile)
                if domain != target and args.recurse:    # Don't scan root domain twice
                    add_target(domain)  # Recursively scan subdomains
            except:
                pass

    def run(self):
        while True:
            try:
                domain = self.queue.get(timeout=1)
            except:
                return
            self.get_name(domain)
            self.queue.task_done()


class output:
    def status(self, message):
        print(col.blue + "[*] " + col.end + message)
        if outfile:
            print("[*] " + message, file=outfile)

    def good(self, message):
        print(col.green + "[+] " + col.end + message)
        if outfile:
            print("[+] " + message, file=outfile)

    def verbose(self, message):
        if args.verbose:
            print(col.brown + "[v] " + col.end + message)
            if outfile:
                print("[v] " + message, file=outfile)

    def warn(self, message):
        print(col.red + "[-] " + col.end + message)
        if outfile:
            print("[-] " + message, file=outfile)

    def fatal(self, message):
        print("\n" + col.red + "FATAL: " + message + col.end)
        if outfile:
            print("FATAL " + message, file=outfile)


class col:
    if sys.stdout.isatty():
        green = '\033[32m'
        blue = '\033[94m'
        red = '\033[31m'
        brown = '\033[33m'
        end = '\033[0m'
    else:   # Colours mess up redirected output, disable them
        green = ""
        blue = ""
        red = ""
        brown = ""
        end = ""


def lookup(domain, recordtype):
    try:
        res = resolver.query(domain, recordtype)
        return res
    except:
        return

def get_wildcard(target):

    # Use current unix time as a test subdomain
    epochtime = str(int(time.time()))
    # Prepend a letter to work around incompetent companies like CableOne
    # and their stupid attempts at DNS hijacking
    res = lookup("a" + epochtime + "." + target, recordtype)
    if res:
        out.good(col.red + "Wildcard" + col.end + " domain found - " + col.brown + res[0].address + col.end)
        return res[0].address
    else:
        out.verbose("No wildcard domain found")

def get_nameservers(target):
    try:
        ns = resolver.query(target, 'NS')
        return ns
    except:
        return

def get_v6(target):
    out.verbose("Getting IPv6 (AAAA) records")
    try:
        res = lookup(target, "AAAA")
        if res:
            out.good("IPv6 (AAAA) records found. Try running dnscan with the "+ col.green + "-6 " + col.end + "option.")
        for v6 in res:
            print(str(v6) + "\n")
            if outfile:
                print(v6, file=outfile)
    except:
        return

def get_txt(target):
    out.verbose("Getting TXT records")
    try:
        res = lookup(target, "TXT")
        if res:
            out.good("TXT records found")
        for txt in res:
            print(txt)
            if outfile:
                print(txt, file=outfile)
        print("")
    except:
        return

def get_mx(target):
    out.verbose("Getting MX records")
    try:
        res = lookup(target, "MX")
    except:
        return
    # Return if we don't get any MX records back
    if not res:
        return
    out.good("MX records found, added to target list")
    for mx in res:
        print(mx.to_text())
        if outfile:
            print(mx.to_text(), file=outfile)
        mxsub = re.search("([a-z0-9\.\-]+)\."+target, mx.to_text(), re.IGNORECASE)
        try:
            if mxsub.group(1) and mxsub.group(1) not in wordlist:
                queue.put(mxsub.group(1) + "." + target)
        except AttributeError:
            pass
    print("")

def zone_transfer(domain, ns):
    out.verbose("Trying zone transfer against " + str(ns))
    try:
        zone = dns.zone.from_xfr(dns.query.xfr(str(ns), domain, relativize=False),
                                 relativize=False)
        out.good("Zone transfer sucessful using nameserver " + col.brown + str(ns) + col.end)
        names = list(zone.nodes.keys())
        names.sort()
        for n in names:
            print(zone[n].to_text(n))    # Print raw zone
            if outfile:
                print(zone[n].to_text(n), file=outfile)
        sys.exit(0)
    except Exception:
        pass

def add_target(domain):
    for word in wordlist:
        queue.put(word + "." + domain)

def add_tlds(domain):
    for tld in wordlist:
        queue.put(domain + "." + tld)

def get_args():
    global args
    
    parser = argparse.ArgumentParser('dnscan.py', formatter_class=lambda prog:argparse.HelpFormatter(prog,max_help_position=40))
    target = parser.add_mutually_exclusive_group(required=True) # Allow a user to specify a list of target domains
    target.add_argument('-d', '--domain', help='Target domain', dest='domain', required=False)
    target.add_argument('-l', '--list', help='File containing list of target domains', dest='domain_list', required=False)
    parser.add_argument('-w', '--wordlist', help='Wordlist', dest='wordlist', required=False)
    parser.add_argument('-t', '--threads', help='Number of threads', dest='threads', required=False, type=int, default=8)
    parser.add_argument('-6', '--ipv6', help='Scan for AAAA records', action="store_true", dest='ipv6', required=False, default=False)
    parser.add_argument('-z', '--zonetransfer', action="store_true", default=False, help='Only perform zone transfers', dest='zonetransfer', required=False)
    parser.add_argument('-r', '--recursive', action="store_true", default=False, help="Recursively scan subdomains", dest='recurse', required=False)
    parser.add_argument('-T', '--tld', action="store_true", default=False, help="Scan for TLDs", dest='tld', required=False)
    parser.add_argument('-o', '--output', help="Write output to a file", dest='output_filename', required=False)
    parser.add_argument('-D', '--domain-first', action="store_true", default=False, help='Output domain first, rather than IP address', dest='domain_first', required=False)
    parser.add_argument('-v', '--verbose', action="store_true", default=False, help='Verbose mode', dest='verbose', required=False)
    args = parser.parse_args()

def setup():
    global targets, wordlist, queue, resolver, recordtype, outfile
    if args.domain:
        targets = [args.domain]
    if args.tld and not args.wordlist:
        args.wordlist = os.path.join(os.path.dirname(os.path.realpath(__file__)), "tlds.txt")
    else:
        if not args.wordlist:   # Try to use default wordlist if non specified
            args.wordlist = os.path.join(os.path.dirname(os.path.realpath(__file__)), "subdomains.txt")
    try:
        wordlist = open(args.wordlist).read().splitlines()
    except:
        out.fatal("Could not open wordlist " + args.wordlist)
        sys.exit(1)

    # Open file handle for output
    try:
        outfile = open(args.output_filename, "w")
    except TypeError:
        outfile = None
    except IOError:
        out.fatal("Could not open output file: " + args.output_filename)
        sys.exit(1)

    # Number of threads should be between 1 and 32
    if args.threads < 1:
        args.threads = 1
    elif args.threads > 32:
        args.threads = 32
    queue = Queue.Queue()
    resolver = dns.resolver.Resolver()
    resolver.timeout = 1

    # Record type
    if args.ipv6:
        recordtype = 'AAAA'
    elif args.tld:
        recordtype = 'NS'
    else:
        recordtype = 'A'


if __name__ == "__main__":
    global wildcard
    out = output()
    get_args()
    setup()
    if args.domain_list:
        out.verbose("Domain list provided, will parse {} for domains.".format(args.domain_list))
        if not os.path.isfile(args.domain_list):
            out.fatal("Domain list {} doesn't exist!".format(args.domain_list))
            sys.exit(1)
        with open(args.domain_list, 'r') as domain_list:
            try:
                targets = list(filter(bool, domain_list.read().split('\n')))
            except Exception as e:
                out.fatal("Couldn't read {}, {}".format(args.domain_list, e))
                sys.exit(1)
    for subtarget in targets:
        global target
        target = subtarget
        out.status("Processing domain {}".format(target))
        if args.tld:
            if "." in target:
                out.warn("Warning: TLD scanning works best with just the domain root")
            out.good("TLD Scan")
            add_tlds(target)
        else:
            queue.put(target)   # Add actual domain as well as subdomains

            nameservers = get_nameservers(target)
            out.good("Getting nameservers")
            targetns = []       # NS servers for target
            try:    # Subdomains often don't have NS recoards..
                for ns in nameservers:
                    ns = str(ns)[:-1]   # Removed trailing dot
                    res = lookup(ns, "A")
                    for rdata in res:
                        targetns.append(rdata.address)
                        print(rdata.address + " - " + col.brown + ns + col.end)
                        if outfile:
                            print(rdata.address + " - " + ns, file=outfile)
                    zone_transfer(target, ns)
            except SystemExit:
                sys.exit(0)
            except:
                out.warn("Getting nameservers failed")
    #    resolver.nameservers = targetns     # Use target's NS servers for lokups
    # Missing results using domain's NS - removed for now
            out.warn("Zone transfer failed\n")
            if args.zonetransfer:
                sys.exit(0)

            get_v6(target)
            get_txt(target)
            get_mx(target)
            wildcard = get_wildcard(target)
            out.status("Scanning " + target + " for " + recordtype + " records")
            add_target(target)

        for i in range(args.threads):
            t = scanner(queue)
            t.setDaemon(True)
            t.start()
        try:
            for i in range(args.threads):
                t.join(1024)       # Timeout needed or threads ignore exceptions
        except KeyboardInterrupt:
            out.fatal("Caught KeyboardInterrupt, quitting...")
            if outfile:
                outfile.close()
            sys.exit(1)
        print("\n")
    if outfile:
        outfile.close()
