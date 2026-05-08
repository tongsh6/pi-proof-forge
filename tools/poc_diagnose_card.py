#!/usr/bin/env python3
"""Diagnose a single job card's full structure."""
from __future__ import annotations

import json, subprocess, sys, tempfile, os
from urllib.parse import quote

DIAGNOSE_JS = r"""
(function() {
    var card = document.querySelector('.job-card-pc-container');
    if (!card) return JSON.stringify({error: 'no .job-card-pc-container found'});
    var html = card.outerHTML.slice(0, 3000);
    var inner = card.innerHTML.slice(0, 3000);
    var text = card.textContent.slice(0, 1000);

    // Find all child elements with distinct class names
    var children = [];
    var walk = function(el, depth) {
        if (depth > 4) return;
        for (var i = 0; i < Math.min(el.children.length, 10); i++) {
            var c = el.children[i];
            children.push({
                depth: depth,
                tag: c.tagName,
                class: (c.className || '').slice(0, 200),
                text: (c.textContent || '').trim().slice(0, 200)
            });
            walk(c, depth + 1);
        }
    };
    walk(card, 0);

    // Company name element
    var companyEl = card.querySelector('[class*="company"], [class*="corp"], [class*="comp"], [data-nick]');
    var companyInfo = companyEl ? {
        tag: companyEl.tagName,
        class: (companyEl.className || '').slice(0, 200),
        text: (companyEl.textContent || '').trim(),
        dataNick: companyEl.getAttribute('data-nick') || '',
        href: companyEl.getAttribute('href') || ''
    } : null;

    return JSON.stringify({
        html: html,
        inner: inner.slice(0, 2500),
        text: text,
        children: children,
        companyElement: companyInfo
    }, null, 2);
})();
"""


def main() -> int:
    keyword = sys.argv[1] if len(sys.argv) > 1 else "Java 后端 上海"
    search_url = f"https://www.liepin.com/zhaopin/?key={quote(keyword)}"

    tmpdir = tempfile.gettempdir()
    js_file = os.path.join(tmpdir, 'liepin_diagnose_card.js')
    with open(js_file, 'w', encoding='utf-8') as f:
        f.write(DIAGNOSE_JS)

    applescript = (
        'tell application "Google Chrome"\n'
        '    activate\n'
        '    set searchWindow to make new window\n'
        '    set searchTab to tab 1 of searchWindow\n'
        f'    set URL of searchTab to "{search_url}"\n'
        '    set maxWait to 15\n'
        '    repeat with i from 1 to maxWait\n'
        '        delay 1\n'
        '        try\n'
        '            set linkCount to execute searchTab javascript "document.querySelectorAll(\'a[href*=\\\"/job/\\\"]\').length"\n'
        '            if linkCount > 0 then exit repeat\n'
        '        end try\n'
        '    end repeat\n'
        '    delay 1\n'
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

    print(f"Diagnosing Liepin job card structure...")
    result = subprocess.run(
        ["osascript", "-e", applescript],
        capture_output=True, text=True, timeout=60,
    )

    if result.returncode != 0:
        print(f"[ERROR] {result.stderr.strip()}")
        return 1

    try:
        data = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        print(f"[PARSE ERROR] {result.stdout[:1000]}")
        return 1

    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
