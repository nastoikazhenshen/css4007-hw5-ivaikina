# HW5 — My LangGraph helpdesk

## Part 1 — How the graph works

### My graph and state

TODO: draw the first graph and explain what each node reads and changes. Answer the four state and routing questions in the brief.

### Predictions before running

| Message | Predicted route | Actual route | What I learned |
| --- | --- | --- | --- |
| I cannot connect to Wi-Fi. | read_request → wifi_help | read_request → wifi_help | The graph detects "Wi-Fi" and retrieves the Wi-Fi instructions from helpdesk.json. |
| I forgot my PASSWORD. | read_request → password_help | read_request → password_help | Routing is case-insensitive because the message is converted to lowercase. |
| My laptop screen is broken. | read_request → other_help | read_request → other_help | Unsupported requests are routed to other_help, which asks for clarification. |
| My Wi-Fi password does not work. | read_request → wifi_help | read_request → wifi_help | When both keywords are present, Wi-Fi takes priority because its condition is checked first. |

All four predicted routes matched the actual execution traces. Each node returned a partial state update, while the graph preserved the existing fields and merged the updates into the current state.

### My change to the graph

TODO: draw the graph with clarify_problem, show the new trace, and explain the difference. What does LangGraph control, and what do my functions decide?

## Part 2 — Model and tools

TODO: draw the model/tool loop. Answer the four questions in the brief. Record the model and provider, direct calls to each tool, and one actual run that uses multiple tools. Explain the loop limit.

## Part 3 — Memory

TODO: explain conversation state, thread_id, user identifier, user preference storage, and retrieval from helpdesk.json.

| Situation | Command used | Log file | What happened |
| --- | --- | --- | --- |
| Refer to an earlier message | | | |
| Close, restart and resume | | | |
| Same user, new conversation | | | |
| Different user | | | |

## Part 4 — Running and checking my work

TODO: point to the README setup steps, package versions, memory-reset instructions, tests and GitHub Actions workflow. Explain which mistake each test catches and which runs use a fake model.

## Choices and limitations

TODO: explain the storage and libraries I chose, why they fit this task, and what still does not work reliably.

## Supplied scenarios — my actual results

| Scenario | Command or manual steps | Log file | What happened / what I changed |
| --- | --- | --- | --- |
| S01 — Simple Wi-Fi route | | | |
| S02 — Case-insensitive password route | | | |
| S03 — Unsupported request | | | |
| S04 — Two topics before the graph change | | | |
| S05 — Two topics after adding clarification | | | |
| S06 — Instructions then local ticket | | | |
| S07 — The same request during a Wi-Fi outage | | | |
| S08 — Status source unavailable | | | |
| S09 — Missing ticket details | | | |
| S10 — Use the current conversation | | | |
| S11 — Persist and recall after restart | | | |
| S12 — Preference across threads without replay | | | |
| S13 — Do not share memory between users | | | |
| S14 — Password recovery outage | | | |
