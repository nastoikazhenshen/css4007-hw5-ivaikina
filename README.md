# HW5 — Build a university IT helpdesk with LangGraph

**CSS-4007 · Artificial Intelligence**  
**Due:** 8 November 2026, 23:59 (UTC+5)

## Start from this repository

1. Fork [ardakshalkar/css4007-hw5](https://github.com/ardakshalkar/css4007-hw5) and keep your fork public, as for the earlier homeworks.
2. Clone your fork and work there. Do not open a pull request to the starter repository.
3. Read [SCENARIOS.md](SCENARIOS.md) to see the example conversations and what the finished application should do.
4. Read [data/README.md](data/README.md), then inspect the supplied JSON files. Use these fixtures for your demonstrations.
5. Write your code and fill in SUBMISSION.md as you complete the parts. The starter supplies the task and data; you implement the graph, tools, memory and tests.

### Set up your environment

Create a virtual environment with python -m venv .venv. Activate it with .venv\Scripts\Activate.ps1 in PowerShell, or source .venv/bin/activate on macOS/Linux. Then run python -m pip install -r requirements.txt.

Part 1 needs no API key. For the model parts, copy .env.example to .env and set your key and an available tool-capable model identifier. The dependency list includes the OpenAI adapter; if you choose another provider, replace it with the appropriate adapter and document your setup. The SQLite checkpoint package is supplied for a local storage option; explain your final storage choice.

The starter dependencies are not a tested, pinned environment for a completed application. Pin the versions you actually use once your code runs, and record your Python version. No application entry point is supplied: include your own exact run commands in your README.

## The scenario

A university IT helpdesk receives messages such as “I cannot connect to Wi-Fi” and “I forgot my password.” The assistant should find the relevant instructions, check whether a service is down, and help prepare a support ticket if the problem remains unresolved. When a user returns, it should remember the conversation and their saved preference for the language of replies.

Build this assistant in stages using **LangGraph**. Start with a small program whose route you can explain. Then add model decisions, tools and memory. A terminal application is enough.

This is a practice version of a real helpdesk workflow. Use the supplied fictional helpdesk information and invented users. It does not connect to the university's systems or submit real tickets.

## Part 1 — Understand how a graph makes a decision

First build a small helpdesk graph **without an LLM**. It handles only Wi-Fi questions and password questions.

Your graph must follow this structure:

```text
START → read_request → choose the next node
                         ├─ wifi_help     → END
                         ├─ password_help → END
                         └─ other_help    → END
```

Use these routing rules:

- If the message contains `wifi` or `wi-fi`, send it to `wifi_help`.
- Otherwise, if it contains `password`, send it to `password_help`.
- Otherwise, send it to `other_help`, which asks the user whether the problem concerns Wi-Fi or a password.
- Ignore differences between uppercase and lowercase letters.

The two help nodes should return the corresponding instructions from `data/helpdesk.json`. Use separate LangGraph nodes and a conditional edge.

### Decide what your state holds

Use at least these fields:

| Field | What it holds |
| --- | --- |
| `message` | The user's original message |
| `category` | The category identified by `read_request` |
| `reply` | The response produced by a help node |

Before writing code, draw the graph and answer:

1. What information does each node need to read? What does it change?
2. What is the difference between a node returning an update to the state and a conditional edge choosing the next node?
3. Does the next node receive only the previous node's update, or the current graph state?
4. What do `START`, `END`, and compiling a graph mean in this program?

### Predict, run, explain

Predict the route for each message before running your code:

- `I cannot connect to Wi-Fi.`
- `I forgot my PASSWORD.`
- `My laptop screen is broken.`
- `My Wi-Fi password does not work.`

Then run all four. For each run, save the order of nodes and the state after each node. Compare it with your prediction. Explain what happens when a message mentions both Wi-Fi and a password, and which rule causes that result.

Now change the graph: when both topics appear, send the request to a new `clarify_problem` node that asks which problem the user wants to solve first. Show the changed graph and the new execution trace.

Finish by explaining **what LangGraph controls here** and **what your own Python functions decide**. There is no model making decisions in this part.

## Part 2 — Let a model choose tools

Extend the same helpdesk with a model that can use three reusable tools:

| Tool | What it does |
| --- | --- |
| `find_instructions` | Looks up Wi-Fi or password instructions in the local helpdesk data |
| `check_service_status` | Looks up whether the requested service is operating or has a known outage |
| `prepare_ticket` | Produces a local ticket draft from the problem description and steps already tried |

Each tool must work when called directly, without the agent. Then connect the tools to the model through your graph. A ticket is a draft saved locally; no message is sent to a real helpdesk.

Show one request that needs more than one tool. For example: “Wi-Fi still does not work after I followed the instructions. Is it down? If it is working, help me prepare a ticket.” The assistant's choice should depend on the tool results.

Draw the execution loop: the model requests a tool, your program runs it, its result returns to the model, and the model either continues or answers. Include a limit so the loop cannot run forever, and explain where you enforce it.

In `SUBMISSION.md`, explain:

1. How does the graph decide between running a tool and ending with an answer?
2. Which component requests a tool, and which component actually executes it?
3. What changes in the state after a tool result returns?
4. What makes this part different from the fixed routing rules in Part 1?

Save an actual run showing the model requests, tool results, and final answer. State which model and provider you used. Use the supplied service-status snapshots to show that the same conditional request leads to different behaviour when Wi-Fi is operating, down, or its status is unknown. See SCENARIOS.md for the interactions.

## Part 3 — Remember the user and the conversation

Add two separate kinds of memory:

- **Conversation memory:** the current problem, previous messages and steps already tried in this conversation.
- **User memory:** a saved preference, such as “reply in Kazakh,” that is available in a later conversation for the same invented user.

Use a LangGraph checkpointer to save conversation state, and persistent storage for the user preference. Explain what a `thread_id` identifies and how it differs from a user identifier. Memory must survive closing and restarting the program.

Demonstrate these situations:

1. A user reports a Wi-Fi problem, then says “I already tried that.” The assistant uses the earlier messages to understand what “that” means.
2. Close the program and start it again. Resume the same conversation with its previous state.
3. Start a new conversation for the same invented user. The saved language preference is available, while the previous conversation is a separate thread.
4. Start a conversation for a different invented user. The first user's preference must not appear.

For each demonstration, show what was read from conversation memory, user memory, or the helpdesk reference file. Explain why looking up Wi-Fi instructions is retrieval, while recalling the user's chosen language is memory.

## Part 4 — Make it easy for someone else to run your work

This means another person can download your code, follow your instructions, and run the same demonstrations on their computer.

In your repository:

1. Add a `README.md` with the exact steps to install the required packages, configure a model API key, start the program, and run the examples. State your Python version.
2. Include a dependency file with the package versions you used. Do not make the reader guess which LangGraph version works with your code.
3. Explain where memory files are saved and how to clear them to start again.
4. Add tests that check routing, the three tools, saved memory after a restart, and separation between users and conversations. Explain what each test would catch if the code broke.
5. Set up GitHub Actions to run these tests automatically whenever you push changes. This is continuous integration, or CI. The tests must work without a private model API key; you may substitute a clearly labelled fake model in tests. Keep the real model demonstration from Part 2 separate.
6. Commit as you complete each stage, with messages explaining what changed.

Keep API keys in environment variables or an ignored `.env` file. Do not commit keys, live memory databases, or personal information. Use invented identifiers such as `demo-user-a` and `demo-user-b` in your saved examples.

## Demonstrate the finished application

Run S01–S14 from data/scenarios.json. Follow reset and restart events as explained in data/README.md. Fill in the scenario table in SUBMISSION.md and save your own logs. SCENARIOS.md shows the expected user experience; it is not a set of measured results.

## What to hand in

Submit your repository link. It should contain:

- Your LangGraph code for all four parts.
- `SUBMISSION.md` with your drawings, explanations and predictions compared with actual runs.
- Small execution logs in `outputs/` showing which nodes and tools ran and what changed in the state.
- Setup instructions, a dependency file, tests and the GitHub Actions workflow.

Push your finished work to your public fork and submit its link on the LMS. The exact HW5 LMS submission destination is still to be provided by the professor.

## References

- [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph memory](https://docs.langchain.com/oss/python/langgraph/add-memory)



---

## Student implementation — run this fork

The starter assignment above is retained unchanged. This section documents the implemented application and its exact run commands.

**Environment:** Python 3.12.16; see \`requirements.txt\` for pinned versions.

### Install

From the repository root, on macOS/Linux:

\`\`\`bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
\`\`\`

On Windows, use \`py -3.12 -m venv .venv\`, activate with \`.venv\Scripts\activate\`, and install with \`python -m pip install -r requirements.txt\`.

For the real model demonstrations, copy \`.env.example\` to \`.env\` (for example, \`cp .env.example .env\`) and set \`OPENAI_API_KEY\` to a **private, newly generated** key and \`MODEL_NAME=gpt-4.1-mini\` (or another available tool-capable OpenAI model). \`.env\` is ignored by Git. **Part 1, direct tools and the automated tests do not need a model API key.** The status snapshots and accounts are fictional.

### Part 1: deterministic graph (no LLM)

\`\`\`bash
python part1.py
python part1.py > outputs/part1_clarification_trace.txt
\`\`\`

The current \`part1.py\` is the modified graph with \`clarify_problem\`. Its original pre-change trace is retained in \`outputs/part1_original_trace.txt\`; see the comparison in \`SUBMISSION.md\`. Both prints include node paths and state updates.

### Part 2: model and tools

\`\`\`bash
python part2.py --direct
python part2.py --scenario S06
python part2.py --scenario S07
python part2.py --scenario S08
python part2.py --scenario S09
python part2.py --scenario S14
\`\`\`

The first command runs the three reusable Python functions directly. The scenario commands call the **real** OpenAI model and produce \`outputs/part2_SXX.json\` containing the node/tool trace and final answers. Ticket drafts are saved to \`local-storage/tickets/DRAFT-*.json\`; nothing is sent.

### Part 3: persistent memory

\`\`\`bash
python part3.py scenario --id S10 --mode real
python part3.py scenario --id S11 --mode real
python part3.py scenario --id S12 --mode real
python part3.py scenario --id S13 --mode real
\`\`\`

The runner uses the supplied \`data/scenarios.json\`, resets storage before each independent scenario, and starts **each message in a separate Python process** to verify disk persistence. It writes \`outputs/part3_SXX_real.json\`.

Use \`--mode fake\` instead of \`--mode real\` for a clearly labelled, deterministic test substitute that needs no API key. To send a manual message in a chosen conversation:

\`\`\`bash
python part3.py chat --mode real --user-id demo-user-a --thread-id my-thread --message "I cannot connect to Wi-Fi."
\`\`\`

Repeat the command with the same user and thread to resume the conversation.

### Memory storage and reset

- \`local-storage/part3-scenarios/SXX/conversations.sqlite\`: LangGraph SQLite checkpoints for a scenario.
- \`local-storage/part3-scenarios/SXX/preferences.sqlite\`: persistent language preferences keyed by \`user_id\`.
- \`local-storage/part3/\`: default persistent storage for manual \`part3.py chat\` calls.
- \`local-storage/tickets/\`: local ticket drafts from Part 2.
- \`outputs/\`: execution traces intended for submission (do not store secrets here).

To reset one scenario's memory, stop any running program and remove only its directory, e.g. \`rm -rf local-storage/part3-scenarios/S11\` on macOS/Linux. To reset all local state, delete the \`local-storage/\` directory **after backing up any drafts you want to keep**. Database and secret files are Git-ignored.

### Automated tests and CI

\`\`\`bash
python -m pytest -v
\`\`\`

\`tests/test_helpdesk.py\` covers graph routing, the three direct tools, ticket validation, restart persistence and separation of users/threads. Tests use a labelled **fake** planner for memory and do **not** call OpenAI. \`.github/workflows/tests.yml\` runs the same tests on every push to \`main\`, on pull requests and on manual workflow dispatch. See \`SUBMISSION.md\` for actual scenario outcomes and limitations.
