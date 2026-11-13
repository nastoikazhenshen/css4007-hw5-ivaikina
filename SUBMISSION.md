# HW5 — My LangGraph helpdesk

**Student:** Darya Ivaikina · **Course:** CSS-4007 · **Python:** 3.12.16

## Part 1 — How the graph works

### My graph and state

**Original graph:**
```text
START → read_request
          ├── wifi_help → END
          ├── password_help → END
          └── other_help → END
```

The state contains `message`, `category`, and `reply`. `read_request` sets the category; help nodes set the reply using `data/helpdesk.json` or a clarification. Nodes return partial updates to the **merged state**; conditional edges select the next node. `START`/`END` mark boundaries, and `compile()` makes the graph executable.

### Predictions before running

| Message | Predicted route | Actual route | What I learned |
| --- | --- | --- | --- |
| I cannot connect to Wi-Fi. | read_request → wifi_help | read_request → wifi_help | Wi-Fi keywords match. |
| I forgot my PASSWORD. | read_request → password_help | read_request → password_help | Matching ignores case. |
| My laptop screen is broken. | read_request → other_help | read_request → other_help | Unsupported topic asks for clarification. |
| My Wi-Fi password does not work. | read_request → wifi_help | read_request → wifi_help | The original Wi-Fi condition takes priority. |

All predictions matched `outputs/part1_original_trace.txt`, which records node updates and the state after each node.

### My change to the graph

**Updated graph:**
```text
START → read_request
          ├── wifi_help → END
          ├── password_help → END
          ├── other_help → END
          └── clarify_problem → END
```

Checking both keywords first sets `category = "both"`: the fourth message follows `read_request → clarify_problem`; other routes stay unchanged. Code: `part1.py`; trace: `outputs/part1_clarification_trace.txt`. LangGraph manages execution and state; Python functions implement the rules. **No LLM is used.**

## Part 2 — Model and tools

**Model/tool graph:**
```text
START → Model
          ├── Tool requested → ToolNode → ToolMessage → Model (loop)
          ├── No tool requested → END
          └── Tool limit reached → END
```

1. The edge checks `AIMessage.tool_calls`: tool calls route to `ToolNode`; otherwise, `END`.
2. The **OpenAI model** requests tools; **ToolNode** executes them.
3. Results enter `MessagesState` as `ToolMessage` for the next model decision.
4. Unlike Part 1's fixed rules, the model selects tools based on the conversation and results.

**Provider/model:** OpenAI, `gpt-4.1-mini` (confirm in run metadata). **Limit:** `MAX_TOOL_ROUNDS = 5`, enforced by `call_model` in `part2.py`.

Direct tests (`python part2.py --direct`): `find_instructions` returned `GUIDE-WIFI`, `check_service_status` returned `operational`, and `save_ticket` (used by `prepare_ticket`) saved an unsent draft (`sent: false`).

**Real-model run S06:** `find_instructions` → `check_service_status` (`operational`) → `prepare_ticket` (`DRAFT-B731C799A449`). The first attempt was rejected for unstated steps; an exact-phrasing prompt fixed it. Other results: S07 (`outage`, no ticket); S08 (`unknown`, draft offered); S09 (details requested, draft `DRAFT-A0460FF8DD3C`); S14 (`account_recovery` outage, no invented repair time).

## Part 3 — Memory

**Conversation memory:** `SqliteSaver` persists messages, problem and steps per `user_id::thread_id`; each `thread_id` denotes one conversation. **User memory:** `preferences.sqlite` persists reply language per `user_id` across threads and restarts.

`capture` updates `problem`, `steps_tried`, `preference` and `memory_source` from the message and stored state. Reading `helpdesk.json` is **retrieval**; recalling Kazakh for `demo-user-a` is **user memory**. Scenarios use separate processes and persistent SQLite.

| Situation | Command used | Log file | What happened |
| --- | --- | --- | --- |
| Refer to an earlier message | `python part3.py scenario --id S10 --mode real` | `outputs/part3_S10_real.json` | Recalled Wi-Fi and attempted steps from the previous message in the same thread (conversation memory). |
| Close, restart and resume | `python part3.py scenario --id S11 --mode real` | `outputs/part3_S11_real.json` | Resumed the same thread in a different process, recalled Wi-Fi/steps and replied in Kazakh (checkpoint + user preference). |
| Same user, new conversation | `python part3.py scenario --id S12 --mode real` | `outputs/part3_S12_real.json` | New thread recalled saved Kazakh preference but did not replay the old Wi-Fi problem (user memory only). |
| Different user | `python part3.py scenario --id S13 --mode real` | `outputs/part3_S13_real.json` | `demo-user-b` had no saved preference or previous problem from `demo-user-a` (isolation). |

## Part 4 — Running and checking my work

`README.md` documents Python 3.12 setup, API configuration, commands and memory reset. `requirements.txt` pins `langgraph==1.2.21`, `langchain-openai==1.8.0`, `langgraph-checkpoint-sqlite==3.1.3`, `python-dotenv==1.2.4` and `pytest==9.2.0`. SQLite and unsent drafts stay in ignored `local-storage/`; deleting a scenario directory resets its memory.

`tests/test_helpdesk.py` tests routing, clarification, three tools, status profiles, ticket validation, restart persistence and user/thread isolation. It catches wrong routes/data, incomplete drafts, lost history and cross-user leakage. Memory tests use a **deterministic fake model**, not OpenAI.

**Tests:** 14/14 passed on Python 3.12.16. **CI:** `.github/workflows/tests.yml` runs keyless pytest on push, pull request and manual trigger. Real OpenAI demonstrations are separate.

## Choices and limitations

LangGraph makes routing traceable; SQLite provides restart-safe local memory. `ChatOpenAI` supports tools; pytest uses a deterministic fake model. **Limitations:** fictional statuses, unsent drafts, variable model wording, limited English step extraction and occasional invalid tool arguments (first S06 attempt). Direct dependencies are pinned, but transitive packages are not locked; SQLite setup is not for production multi-worker use.

## Supplied scenarios — my actual results

| Scenario | Command or manual steps | Log file | What happened / what I changed |
| --- | --- | --- | --- |
| S01 — Simple Wi-Fi route | Original Part 1 run | `outputs/part1_original_trace.txt` | `read_request → wifi_help`; Wi-Fi guide returned. |
| S02 — Case-insensitive password route | Original Part 1 run | `outputs/part1_original_trace.txt` | `PASSWORD` routed to `password_help`. |
| S03 — Unsupported request | Original Part 1 run | `outputs/part1_original_trace.txt` | `other_help` requested clarification. |
| S04 — Two topics before the graph change | Original Part 1 run | `outputs/part1_original_trace.txt` | `wifi_help` won the original precedence. |
| S05 — Two topics after adding clarification | `python part1.py` | `outputs/part1_clarification_trace.txt` | `category="both"`; `clarify_problem` executed. |
| S06 — Instructions then local ticket | `python part2.py --scenario S06` | `outputs/part2_S06.json` | Instructions, operational status and unsent draft after fixing exact-step prompt. |
| S07 — The same request during a Wi-Fi outage | `python part2.py --scenario S07` | `outputs/part2_S07.json` | Outage, no conditional draft. |
| S08 — Status source unavailable | `python part2.py --scenario S08` | `outputs/part2_S08.json` | Unknown status; alternative draft offered after prompt adjustment. |
| S09 — Missing ticket details | `python part2.py --scenario S09` | `outputs/part2_S09.json` | Asked for required details; then saved a draft with stated steps. |
| S10 — Use the current conversation | `python part3.py scenario --id S10 --mode real` | `outputs/part3_S10_real.json` | Correctly recalled previous troubleshooting. |
| S11 — Persist and recall after restart | `python part3.py scenario --id S11 --mode real` | `outputs/part3_S11_real.json` | Same thread recovered in new process; Kazakh answer. |
| S12 — Preference across threads without replay | `python part3.py scenario --id S12 --mode real` | `outputs/part3_S12_real.json` | Kazakh preference persisted in new thread; previous issue not replayed. |
| S13 — Do not share memory between users | `python part3.py scenario --id S13 --mode real` | `outputs/part3_S13_real.json` | No user-memory leakage to `demo-user-b`. |
| S14 — Password recovery outage | `python part2.py --scenario S14` | `outputs/part2_S14.json` | Detected `account_recovery` outage without inventing repair time. |
