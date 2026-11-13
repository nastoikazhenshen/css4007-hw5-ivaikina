
import argparse
import json
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition


ROOT = Path(__file__).resolve().parent
MAX_TOOL_ROUNDS = 5


def load_json(filename):
    path = ROOT / "data" / filename
    return json.loads(path.read_text(encoding="utf-8"))


def lookup_instructions(topic):
    topic = topic.lower().replace("-", "")

    data = load_json("helpdesk.json")
    instructions = data["instructions"].get(topic)

    if instructions is None:
        return {"error": "Unknown topic"}

    return {
        "topic": topic,
        "instruction_id": instructions["instruction_id"],
        "steps": instructions["steps"],
        "source": "data/helpdesk.json",
    }


def lookup_status(service, profile):
    profiles = load_json("service_status.json")["profiles"]

    if profile not in profiles:
        return {"error": "Unknown status profile"}

    result = profiles[profile].get(service)

    if result is None:
        return {"error": "Unknown service"}

    return {
        "service": service,
        "status": result["status"],
        "message": result["message"],
        "profile": profile,
        "source": "data/service_status.json",
    }


def save_ticket(
    problem,
    steps,
    user_id,
    thread_id,
    profile,
    service_status,
):
    if not problem.strip() or not steps:
        return {
            "error": "Problem description and attempted steps are required."
        }

    category = "other"
    lower = problem.lower()

    if "wifi" in lower or "wi-fi" in lower:
        category = "wifi"
    elif "password" in lower or "recovery" in lower:
        category = "password"

    template = load_json("ticket_template.json")["ticket"]
    ticket = dict(template)

    ticket_id = "DRAFT-" + uuid.uuid4().hex[:12].upper()

    reference_ids = []
    if category in ("wifi", "password"):
        reference_ids.append(
            lookup_instructions(category)["instruction_id"]
        )

    ticket.update({
        "ticket_id": ticket_id,
        "status": "draft",
        "user_id": user_id,
        "thread_id": thread_id,
        "category": category,
        "summary": problem,
        "steps_tried": steps,
        "service_status": service_status,
        "status_profile": profile,
        "reference_ids": reference_ids,
    })

    directory = ROOT / "local-storage" / "tickets"
    directory.mkdir(parents=True, exist_ok=True)

    path = directory / f"{ticket_id}.json"
    path.write_text(
        json.dumps(ticket, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "ticket_id": ticket_id,
        "file": str(path),
        "status": "draft",
        "sent": False,
    }


def build_graph(profile, user_id, thread_id):
    context = {
        "checked_status": None,
        "conditional_ticket": False,
        "user_messages": [],
        "tool_rounds": 0,
    }

    @tool
    def find_instructions(topic: str) -> dict:
        """Retrieve local instructions for wifi or password."""
        return lookup_instructions(topic)

    @tool
    def check_service_status(service: str) -> dict:
        """Check fictional service status for wifi or account_recovery."""
        result = lookup_status(service, profile)
        context["checked_status"] = result.get("status")
        return result

    @tool
    def prepare_ticket(
        problem_description: str,
        steps_tried: list[str],
    ) -> dict:
        """Create an unsent local support ticket draft."""
        if (
            context["conditional_ticket"]
            and context["checked_status"] != "operational"
        ):
            return {
                "error": "Conditional ticket requires confirmed operational status."
            }

        user_text = " ".join(context["user_messages"]).lower()

        for step in steps_tried:
            if step.strip().lower() not in user_text:
                return {
                    "error": (
                        "Use only exact troubleshooting steps "
                        "stated by the user."
                    )
                }

        return save_ticket(
            problem_description,
            steps_tried,
            user_id,
            thread_id,
            profile,
            context["checked_status"] or "not_checked",
        )

    tools = [
        find_instructions,
        check_service_status,
        prepare_ticket,
    ]

    load_dotenv(ROOT / ".env")

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is missing from .env")

    model_name = os.getenv("MODEL_NAME") or "gpt-4.1-mini"

    model = ChatOpenAI(
        model=model_name,
        temperature=0,
    ).bind_tools(
        tools,
        parallel_tool_calls=False,
    )

    system_prompt = """
You are a fictional university IT helpdesk assistant.

Use the provided tools to retrieve instructions, check
service status, and prepare local ticket drafts.

The service information is fictional and not live.

Never invent instructions, troubleshooting attempts,
service outages, repair times, or ticket details.

For a conditional request such as "if the service is
operating, prepare a ticket", check the service first.
Only prepare the ticket if its status is operational.

If the status is outage or unknown, do not create the
conditional ticket.

If service status is unknown, explain that it could not
be verified. Offer to prepare a separate ticket draft
describing the unavailable status.

Do not create this draft without user confirmation.
Do not say that creating any ticket is impossible.

If ticket information is missing, ask the user for it.

When preparing a ticket, the steps_tried list must contain
only exact substrings copied from the user's messages.

Never paraphrase troubleshooting steps.
Never include steps from find_instructions unless the user
explicitly confirms performing them.

For example, if the user says:
"I enabled Wi-Fi and forgot the saved network"

The steps_tried list must be:
["enabled Wi-Fi", "forgot the saved network"]

Do not add "airplane mode is off" or "tried reconnecting"
unless the user explicitly said so.

If prepare_ticket returns a validation error, retry with
the exact user wording. Do not ask the user to repeat
information they already provided.

Tickets are local drafts only. Never claim they were sent.
Never request passwords or recovery codes.

You may call multiple tools sequentially when necessary.
"""

    def call_model(state: MessagesState):
        if (
            context["tool_rounds"] >= MAX_TOOL_ROUNDS
            and isinstance(state["messages"][-1], ToolMessage)
        ):
            return {
                "messages": [
                    AIMessage(
                        content="Tool loop limit reached."
                    )
                ]
            }

        response = model.invoke([
            SystemMessage(content=system_prompt),
            *state["messages"],
        ])

        if response.tool_calls:
            context["tool_rounds"] += 1

        return {"messages": [response]}

    builder = StateGraph(MessagesState)

    builder.add_node("model", call_model)
    builder.add_node("tools", ToolNode(tools))

    builder.add_edge(START, "model")

    builder.add_conditional_edges(
        "model",
        tools_condition,
        {
            "tools": "tools",
            "__end__": END,
        },
    )

    builder.add_edge("tools", "model")

    return builder.compile(), context, model_name


def serialize_message(message):
    result = {
        "type": message.__class__.__name__,
        "content": message.content,
    }

    if isinstance(message, AIMessage):
        result["tool_calls"] = [
            {
                "name": call["name"],
                "args": call["args"],
            }
            for call in message.tool_calls
        ]

    if isinstance(message, ToolMessage):
        result["tool_name"] = message.name

    return result


def run_scenario(scenario_id):
    scenarios = load_json("scenarios.json")["scenarios"]

    scenario = next(
        (item for item in scenarios if item["id"] == scenario_id),
        None,
    )

    if scenario is None or scenario["part"] != 2:
        raise ValueError("Choose S06, S07, S08, S09 or S14.")

    events = [
        event for event in scenario["events"]
        if event["action"] == "message"
    ]

    profile = scenario["status_profile"]
    user_id = events[0]["user_id"]
    thread_id = events[0]["thread_id"]

    graph, context, model_name = build_graph(
        profile, user_id, thread_id
    )

    history = []
    results = []

    for event in events:
        question = event["message"]

        context["checked_status"] = None
        context["tool_rounds"] = 0
        context["conditional_ticket"] = (
            "if it is operating" in question.lower()
            or "if it is working" in question.lower()
        )
        context["user_messages"].append(question)

        history.append(HumanMessage(content=question))

        print("\nUSER:", question)

        trace = []

        for update in graph.stream(
            {"messages": history},
            stream_mode="updates",
        ):
            for node, changes in update.items():
                for message in changes.get("messages", []):
                    record = {
                        "node": node,
                        **serialize_message(message),
                    }

                    trace.append(record)
                    history.append(message)

                    print(json.dumps(
                        record,
                        ensure_ascii=False,
                        indent=2,
                    ))

        answers = [
            message for message in history
            if isinstance(message, AIMessage)
            and message.content
        ]

        final_answer = (
            answers[-1].content if answers else "No final answer"
        )

        print("\nFINAL ANSWER:", final_answer)

        results.append({
            "user_message": question,
            "trace": trace,
            "final_answer": final_answer,
            "loop_limit_reached": (
                final_answer == "Tool loop limit reached."
            ),
        })

    report = {
        "scenario": scenario_id,
        "provider": "OpenAI",
        "model": model_name,
        "status_profile": profile,
        "user_id": user_id,
        "thread_id": thread_id,
        "results": results,
    }

    output_dir = ROOT / "outputs"
    output_dir.mkdir(exist_ok=True)

    output_path = output_dir / f"part2_{scenario_id}.json"
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\nSAVED TRACE:", output_path)


def test_tools_directly():
    print("\nFIND INSTRUCTIONS")
    print(json.dumps(
        lookup_instructions("wifi"),
        indent=2,
    ))

    print("\nCHECK SERVICE STATUS")
    print(json.dumps(
        lookup_status("wifi", "normal"),
        indent=2,
    ))

    print("\nPREPARE TICKET")
    print(json.dumps(
        save_ticket(
            "Cannot connect to Wi-Fi",
            ["Enabled Wi-Fi", "Forgot the saved network"],
            "demo-user-a",
            "direct-test",
            "normal",
            "operational",
        ),
        indent=2,
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--direct", action="store_true")
    parser.add_argument(
        "--scenario",
        choices=["S06", "S07", "S08", "S09", "S14"],
        default="S06",
    )

    args = parser.parse_args()

    if args.direct:
        test_tools_directly()
    else:
        run_scenario(args.scenario)
