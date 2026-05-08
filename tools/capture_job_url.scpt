-- capture_job_url.scpt
-- Save the current Chrome tab's Liepin job URL to job_leads/
-- Usage: osascript tools/capture_job_url.scpt
--   While on a Liepin job page in Chrome, run this to capture the URL.

tell application "Google Chrome"
    set currentURL to URL of active tab of window 1
    set pageTitle to title of active tab of window 1
end tell

if currentURL does not contain "liepin.com/job/" then
    display dialog "Not a Liepin job page. Current URL: " & currentURL buttons {"OK"} default button "OK"
    return
end if

-- Write to job_leads
set timestamp to do shell script "date +%s"
set leadFile to "job_leads/jl-captured-" & timestamp & ".yaml"
set yamlContent to "# Captured from Chrome on " & (current date as string) & "
items:
  - job_url: \"" & currentURL & "\"
    position: \"" & pageTitle & "\"
    direction: backend
    confidence: 0.8
"

do shell script "echo " & quoted form of yamlContent & " >> " & leadFile
display dialog "Saved: " & leadFile & return & return & pageTitle buttons {"OK"} default button "OK"
