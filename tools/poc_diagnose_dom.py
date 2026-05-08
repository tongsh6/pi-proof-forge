#!/usr/bin/env python3
"""Diagnose Liepin search page DOM structure to fix selectors."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import os
from urllib.parse import quote


DIAGNOSE_JS = r"""
(function() {
    var info = {};
    info.pageTitle = document.title;
    info.url = window.location.href;

    var jobLinks = document.querySelectorAll('a[href*="/job/"]');
    info.jobLinkCount = jobLinks.length;

    // Find unique class names related to job/card/list/item
    var classNames = new Set();
    var allEls = document.querySelectorAll('[class]');
    for (var i = 0; i < Math.min(allEls.length, 500); i++) {
        var cls = allEls[i].className;
        if (typeof cls === 'string' && cls) {
            cls.split(/\s+/).forEach(function(c) {
                if (!c) return;
                var lc = c.toLowerCase();
                if (lc.indexOf('job') > -1 || lc.indexOf('card') > -1 ||
                    lc.indexOf('list') > -1 || lc.indexOf('item') > -1) {
                    classNames.add(c);
                }
            });
        }
    }
    info.relevantClassNames = Array.from(classNames).sort();

    info.isCaptcha = window.location.href.indexOf('captcha') > -1;

    // First 3 job links: walk up to find container with data attributes
    var first3 = [];
    for (var j = 0; j < Math.min(jobLinks.length, 3); j++) {
        var link = jobLinks[j];
        var item = {};
        item.href = link.href.split('?')[0];
        item.linkText = (link.textContent || '').trim().slice(0, 80);

        var parent = link;
        for (var d = 0; d < 5; d++) {
            parent = parent.parentElement;
            if (!parent) break;
            var level = 'L' + d;
            item[level + '_tag'] = parent.tagName;
            item[level + '_class'] = (parent.className || '').slice(0, 150);
            if (parent && parent.attributes) {
                for (var a = 0; a < parent.attributes.length; a++) {
                    var attr = parent.attributes[a];
                    if (attr.name.indexOf('data-') === 0) {
                        if (!item._data) item._data = {};
                        item._data[attr.name] = attr.value.slice(0, 100);
                    }
                }
            }
        }
        first3.push(item);
    }
    info.first3Links = first3;

    return JSON.stringify(info, null, 2);
})();
"""


def main() -> int:
    keyword = sys.argv[1] if len(sys.argv) > 1 else "Java 后端 上海"
    search_url = f"https://www.liepin.com/zhaopin/?key={quote(keyword)}"

    tmpdir = tempfile.gettempdir()
    js_file = os.path.join(tmpdir, 'liepin_diagnose.js')
    with open(js_file, 'w', encoding='utf-8') as f:
        f.write(DIAGNOSE_JS)

    # Exact same pattern as poc_liepin_applescript_search.py — osascript -e with inline script
    applescript = (
        'tell application "Google Chrome"\n'
        '    activate\n'
        '    set searchWindow to make new window\n'
        '    set searchTab to tab 1 of searchWindow\n'
        f'    set URL of searchTab to "{search_url}"\n'
        '    delay 3\n'
        '    set rawJson to "{}"\n'
        '    try\n'
        f'        set jsCode to read "{js_file}"\n'
        '        set rawJson to execute searchTab javascript jsCode\n'
        '    on error errMsg\n'
        '        set rawJson to "{\\"error\\": \\"" & errMsg & "\\"}"\n'
        '    end try\n'
        '    close searchWindow\n'
        '    return rawJson\n'
        'end tell'
    )

    print(f"Diagnosing Liepin search page DOM for keyword: {keyword}")
    print()

    result = subprocess.run(
        ["osascript", "-e", applescript],
        capture_output=True, text=True, timeout=60,
    )

    if result.returncode != 0:
        print(f"[ERROR] rc={result.returncode}: {result.stderr.strip()}")
        return 1

    stdout = result.stdout.strip()
    if not stdout:
        print("[WARN] Empty output")
        return 1

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        print(f"[PARSE ERROR] Raw (first 2000 chars):")
        print(stdout[:2000])
        return 1

    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
