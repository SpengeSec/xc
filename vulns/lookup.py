#!/usr/bin/python3
#
# This software is provided under under the BSD 3-Clause License.
# See the accompanying LICENSE file for more information.
#
# Windows Exploit Suggester - Next Generation
#
# Author: Arris Huijgen (@bitsadmin)
# Website: https://github.com/bitsadmin
# 
# Microsoft Update Catalog lookup feature developed by Dominic Breuker
# Website: https://github.com/DominicBreuker
#
# Modified by xct @xct_de (output altered slightly so we can copy paste)

from __future__ import print_function

import sys
import re

try:
    import mechanicalsoup
except ImportError:
    print("[!] Cannot lookup superseeding KBs in the Microsoft Update Catalog!")
    print("    Reason: Python package mechanicalsoup not installed.")
    print("    Install with 'pip install mechanicalsoup' and run again")
    sys.exit(1)


# Progress is a simple progress bar
class Progress:
    # __init__ creates a new progress bar
    # it starts printing immediately, so create it the moment you
    # want to display it
    #
    # name: a human readable name of the progress bar
    # width: the number of steps needed to progress
    def __init__(self, name="", width=40):
        self.name = name
        self.width = width
        self.progress = 0

        sys.stdout.write("{} [{}]".format(self.name, " " * self.width))
        sys.stdout.flush()
        sys.stdout.write("\b" * (self.width + 1))

    # step moves progress forward
    def step(self):
        if self.progress >= self.width:
            return

        sys.stdout.write(".")
        sys.stdout.flush()
        self.progress += 1

    # finish terminates the progress bar
    #
    # msg: a message to append to the output
    def finish(self, msg=""):
        sys.stdout.write("] " + msg + "\n")


# some header values Mirosoft seems to like in the header (not extensively tested)
default_headers = {
    "authority": "www.catalog.update.microsoft.com",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.90 Safari/537.36",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-site": "none",
}

# global browser used to scrape the Microsoft Update Catalog
browser = mechanicalsoup.StatefulBrowser()

# global dict of KBs with their superseeding KBs
superseeded_by = {}

# apply_muc_filter filters the CVEs found by looking up superseeding hotfixes in the
# Microsoft Update Catalog. It returns the CVE iff no superseeding hotfixes are installed.
#
# found: list of CVEs as created by the main script wes.py
# kbs_installed: list of installed hotfixes as seen in systeminfo output
def apply_muc_filter(found, kbs_installed):
    if not found:
        return []

    if not kbs_installed:
        kbs_installed = []

    kbs_installed = set(kbs_installed)

    global superseeded_by
    for cve in found:
        kb = cve["BulletinKB"]
        if kb not in superseeded_by:
            superseeded_by[kb] = set(lookup_supersedence(kb))

    return [
        cve
        for cve in found
        if not (superseeded_by[cve["BulletinKB"]] & kbs_installed)
    ]


# lookup_supersedence returns a list of all KBs superseeding the given KB
# iterates over entries for all Mirosoft products. That is, it does not
# attempt to identify the product. My assumption is that if we return KBs
# that do not apply to the system under anaylsis then this KB will not be
# present on that system so that the result remains the same.
# For example, if we return a KB only applicable to Windows Server 2016,
# not to Windows 10, then this KB will not be installed on the system
# and accordingly the CVE will not be filtered.
#
# kb: the KB to be looked up
def lookup_supersedence(kb):
    browser.open(
        "https://www.catalog.update.microsoft.com/Search.aspx?q={}".format(kb),
        headers=default_headers,
    )
    rows = browser.get_current_page().find(id="ctl00_catalogBody_updateMatches")
    if rows is None:
        return []
    updates = rows.find_all(
        "a", {"onclick": re.compile(r"goToDetails\(\"[a-zA-Z0-9-]+\"\)")}
    )
    ids = [a["id"].split("_")[0] for a in updates]

    kbids = set()
    p = Progress(
        name="    - Looking up potentially missing KB"
        + kb
        + " ",
        width=len(ids),
    )
    for uid in ids:
        kbids = kbids.union(lookup_supersedence_by_uid(uid))
        p.step()

    p.finish(msg="found: [" + ", ".join(kbids) + "]")

    return [kbid.lstrip("KB") for kbid in kbids]


# lookup_supersedence_by_uid looks up a list of superseeding KBs for a
# Microsoft Update ID. The Microsoft Update Catalog seems to close over
# transitive supersedence relationships so there is not need for recursive
# lookups.
#
# uid: the Microsoft Update ID of the update to check
def lookup_supersedence_by_uid(uid):
    browser.open(
        "https://www.catalog.update.microsoft.com/ScopedViewInline.aspx?updateid={}".format(
            uid
        ),
        headers=default_headers,
    )
    supers = browser.get_current_page().find_all("div", {"id": "supersededbyInfo"})
    if len(supers) != 1:
        return set()

    s = supers[0]
    kbids = re.findall("(KB[0-9]+)", s.text.strip())
    if len(kbids) < 1:
        kbids = []
    return set(kbids)


# can also run standalone to check single KB
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Run this script with a Microsoft HotfixID as the single argument")
        print("Example: python lookup.py KB4515384")
        sys.exit(1)

    kb = re.sub('KB', '', sys.argv[1], flags=re.IGNORECASE)
    kbids = lookup_supersedence(kb)
    print("")
    out = f'supersedence = append(supersedence, "{sys.argv[1]}", '
    for kbid in kbids:
        out += f'"KB{kbid}",'
    out += ")"
    print(out)