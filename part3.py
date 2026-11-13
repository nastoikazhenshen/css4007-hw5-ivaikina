import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from part2 import ROOT, load_json, lookup_instructions, lookup_status, save_ticket


class MemoryState(MessagesState):
    preference: Optional[str]
    problem: str
    steps_tried: list[str]
    memory_source: dict
    tool_rounds: int


def get_preference(storage: Path, user_id: str) -> Optional[str]:
    storage.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(storage / "preferences.sqlite") as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS preferences "
            "(user_id TEXT PRIMARY KEY, language TEXT NOT NULL)"
        )
        row = conn.execute(
            "SELECT language FROM preferences WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row[0] if row else None


def set_preference(storage: Path, user_id: str, language: str) -> None:
    get_preference(storage, user_id)
    with sqlite3.connect(storage / "preferences.sqlite") as conn:
        conn.execute(
            "INSERT INTO preferences(user_id,language) VALUES (?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET language=excluded.language",
            (user_id, language),
        )


def parse_steps(text: str) -> list[str]:
    low = text.lower()
    phrases = [
        "enabled wi-fi", "enabled it", "forgot the saved network",
        "tried reconnecting", "reconnecting failed", "reconnected",
    ]
    return [p for p in phrases if p in low and not (
        p == "reconnected" and "reconnecting" in low
    )]


def extract_language(text: str) -> Optional[str]:
    low = text.lower()
    for language in ("Kazakh", "Russian", "English"):
        if f"prefer replies in {language.lower()}" in low or f"reply in {language.lower()}" in low:
            return language
    return None


def fake_answer(state: MemoryState) -> AIMessage:
    latest_human = next(
        (str(m.content) for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), ""
    )
    low = latest_human.lower()
    pref = state.get("preference")
    problem = state.get("problem", "")
    steps = state.get("steps_tried", [])
    if isinstance(state["messages"][-1], ToolMessage):
        return AIMessage(content="The requested reference information was retrieved from the local fixture.")
    if "have i told you" in low or "previous problem" in low:
        if not pref and not problem:
            return AIMessage(content="No preferred language or previous problem has been recorded for this user.")
        return AIMessage(content=f"Language: {pref or 'not set'}. Problem: {problem or 'not recorded'}.")
    if "which language" in low:
        return AIMessage(content=("Сіз қазақ тілін таңдадыңыз." if pref == "Kazakh" else
                                  f"Saved preference: {pref or 'none'}."))
    if "which problem" in low or "which steps" in low or "already tried that" in low:
        details = ", ".join(steps) if steps else "no steps recorded"
        if pref == "Kazakh":
            return AIMessage(content=f"Бұрынғы мәселе: {problem}. Жасалған қадамдар: {details}.")
        return AIMessage(content=f"Previous problem: {problem}. Steps tried: {details}.")
    if "wi-fi" in low or "wifi" in low:
        return AIMessage(content="", tool_calls=[{
            "name": "find_instructions", "args": {"topic": "wifi"},
            "id": "call_" + uuid.uuid4().hex[:16], "type": "tool_call",
        }])
    return AIMessage(content="I can help with Wi-Fi, password recovery, and ticket drafts.")


def build_graph(storage: Path, user_id: str, thread_id: str, profile: str, mode: str):
    context = {"checked_status": "not_checked", "conditional": False,
               "user_text": "", "problem": "", "steps": []}

    @tool
    def find_instructions(topic: str) -> dict:
        """Retrieve Wi-Fi or password instructions from the fictional local guide."""
        return lookup_instructions(topic)

    @tool
    def check_service_status(service: str) -> dict:
        """Retrieve the fictional status of wifi or account_recovery."""
        result = lookup_status(service, profile)
        context["checked_status"] = result.get("status", "unknown")
        return result

    @tool
    def prepare_ticket(problem_description: str, steps_tried: list[str]) -> dict:
        """Save an unsent local ticket draft using only steps explicitly provided by the user."""
        if context["conditional"] and context["checked_status"] != "operational":
            return {"error": "Conditional ticket requires confirmed operational status."}
        for step in steps_tried:
            if step.lower().strip() not in context["user_text"].lower():
                return {"error": "Only use exact user-stated troubleshooting steps."}
        return save_ticket(problem_description, steps_tried, user_id, thread_id,
                           profile, context["checked_status"])

    tools = [find_instructions, check_service_status, prepare_ticket]
    if mode == "real":
        load_dotenv(ROOT / ".env")
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY missing from .env")
        from langchain_openai import ChatOpenAI
        model = ChatOpenAI(
            model=os.getenv("MODEL_NAME") or "gpt-4.1-mini", temperature=0
        ).bind_tools(tools, parallel_tool_calls=False)

    def capture(state: MemoryState) -> dict:
        latest = next(
            (str(m.content) for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), ""
        )
        preferred = extract_language(latest)
        if preferred:
            set_preference(storage, user_id, preferred)
        saved_pref = get_preference(storage, user_id)
        old_problem = state.get("problem", "")
        was_problem = any(p in latest.lower() for p in (
            "cannot connect", "my issue is", "the issue is", "i have a wi-fi problem",
            "i have a wifi problem", "recovery page is unavailable",
        ))
        problem = latest if was_problem else old_problem
        steps = list(state.get("steps_tried") or [])
        for step in parse_steps(latest):
            if step not in steps:
                steps.append(step)
        context.update({
            "checked_status": "not_checked",
            "conditional": "if it is operating" in latest.lower(),
            "problem": problem, "steps": steps,
            "user_text": " ".join(str(m.content) for m in state["messages"]
                                  if isinstance(m, HumanMessage)),
        })
        return {
            "preference": saved_pref, "problem": problem,
            "steps_tried": steps, "tool_rounds": 0,
            "memory_source": {
                "user_preference": ("current_message" if preferred else
                                    "preferences.sqlite" if saved_pref else "none"),
                "conversation": "current_message" if was_problem else
                                "checkpointer" if old_problem else "none",
                "reference": "data/helpdesk.json (via find_instructions)",
            },
        }

    def call_model(state: MemoryState) -> dict:
        if state.get("tool_rounds", 0) >= 5 and isinstance(state["messages"][-1], ToolMessage):
            return {"messages": [AIMessage(content="Tool loop limit reached.")]}
        if mode == "fake":
            answer = fake_answer(state)
        else:
            system = SystemMessage(content=(
                "You are a fictional university IT helpdesk assistant. Use tools for "
                "instructions, service status and local unsent ticket drafts. "
                "Never invent troubleshooting steps, repair times, or saved memories. "
                "For memory questions, use only the current thread state and the user's "
                "stored preference. A new thread must not inherit the old problem. "
                "Do not pretend retrieval is conversation memory. If a language preference "
                "is saved, respond entirely in that language. "
                f"Current user's saved language: {state.get('preference') or 'none'}. "
                f"Problem in this thread: {state.get('problem') or 'none'}. "
                f"Troubleshooting steps in this thread: {state.get('steps_tried') or []}. "
                "When a ticket is conditional on operational status, check status first; "
                "never draft it for outage or unknown. "
                "If ticket data is missing, ask for it."
            ))
            answer = model.invoke([system, *state["messages"]])
        return {"messages": [answer], "tool_rounds": state.get("tool_rounds", 0) +
                (1 if answer.tool_calls else 0)}

    def route(state: MemoryState) -> str:
        if state.get("tool_rounds", 0) > 5:
            return "end"
        return tools_condition(state)

    builder = StateGraph(MemoryState)
    builder.add_node("capture", capture)
    builder.add_node("model", call_model)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "capture")
    builder.add_edge("capture", "model")
    builder.add_conditional_edges("model", route, {"tools": "tools", "__end__": END, "end": END})
    builder.add_edge("tools", "model")
    return builder


def encode(message) -> dict:
    result = {"type": type(message).__name__, "content": str(message.content)}
    if isinstance(message, AIMessage):
        result["tool_calls"] = [{"name": x["name"], "args": x["args"]}
                                for x in message.tool_calls]
    if isinstance(message, ToolMessage):
        result["tool_name"] = message.name
    return result


def chat(message: str, user_id: str, thread_id: str,
         profile: str, mode: str, storage: Path) -> dict:
    storage.mkdir(parents=True, exist_ok=True)
    trace = []
    with SqliteSaver.from_conn_string(str(storage / "conversations.sqlite")) as saver:
        app = build_graph(storage, user_id, thread_id, profile, mode).compile(checkpointer=saver)
        config = {"configurable": {"thread_id": user_id + "::" + thread_id},
                  "recursion_limit": 20}
        for event in app.stream({"messages": [HumanMessage(content=message)]},
                                config, stream_mode="updates"):
            for node, changes in event.items():
                trace.append({
                    "node": node,
                    "updates": {
                        key: ([encode(x) for x in value] if key == "messages" else value)
                        for key, value in (changes or {}).items()
                    },
                })
        state = app.get_state(config).values
    last_answers = [m for m in state["messages"]
                    if isinstance(m, AIMessage) and m.content]
    return {
        "user_id": user_id, "thread_id": thread_id, "profile": profile,
        "mode": mode, "process_id": os.getpid(), "trace": trace,
        "saved_preference": state.get("preference"),
        "saved_problem": state.get("problem", ""),
        "saved_steps": state.get("steps_tried", []),
        "memory_source": state.get("memory_source", {}),
        "reply": str(last_answers[-1].content) if last_answers else "",
    }


def scenario_run(scenario_id: str, mode: str, storage: Path) -> dict:
    data = load_json("scenarios.json")["scenarios"]
    item = next((x for x in data if x["id"] == scenario_id and x["part"] == 3), None)
    if item is None:
        raise ValueError("Part 3 scenarios: S10, S11, S12, S13")
    directory = storage / scenario_id
    if item["reset_before"] and directory.exists():
        shutil.rmtree(directory)
    events = []
    for e in item["events"]:
        if e["action"] == "restart_process":
            events.append({"action": "restart_process", "disk_preserved": True})
            continue
        cmd = [sys.executable, str(ROOT / "part3.py"), "chat", "--mode", mode,
               "--storage", str(directory), "--user-id", e["user_id"],
               "--thread-id", e["thread_id"], "--profile", item["status_profile"],
               "--message", e["message"]]
        proc = subprocess.run(cmd, text=True, capture_output=True, check=True, cwd=ROOT)
        events.append({"action": "message", "command": " ".join(cmd),
                       "message": e["message"], "result": json.loads(proc.stdout)})
    output = {"scenario": scenario_id, "mode": mode, "events": events}
    out_dir = ROOT / "outputs"
    out_dir.mkdir(exist_ok=True)
    output_path = out_dir / f"part3_{scenario_id}_{mode}.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"saved_log": str(output_path),
            "replies": [e["result"]["reply"] for e in events if e["action"] == "message"],
            "process_ids": [e["result"]["process_id"] for e in events if e["action"] == "message"]}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("chat")
    p.add_argument("--message", required=True)
    p.add_argument("--user-id", default="demo-user-a")
    p.add_argument("--thread-id", default="demo-thread")
    p.add_argument("--profile", default="normal")
    p.add_argument("--mode", choices=["fake", "real"], default="real")
    p.add_argument("--storage", type=Path, default=Path("local-storage/part3"))
    d = sub.add_parser("scenario")
    d.add_argument("--id", choices=["S10", "S11", "S12", "S13"], required=True)
    d.add_argument("--mode", choices=["fake", "real"], default="real")
    d.add_argument("--storage", type=Path, default=Path("local-storage/part3-scenarios"))
    args = parser.parse_args()
    if args.command == "chat":
        result = chat(args.message, args.user_id, args.thread_id,
                      args.profile, args.mode, args.storage)
    else:
        result = scenario_run(args.id, args.mode, args.storage)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
