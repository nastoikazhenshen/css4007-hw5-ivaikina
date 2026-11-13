import json
from pathlib import Path
from typing import TypedDict

from langgraph.graph import StateGraph, START, END


class HelpdeskState(TypedDict, total=False):
    message: str
    category: str
    reply: str


DATA_PATH = Path(__file__).parent / "data" / "helpdesk.json"

with open(DATA_PATH, "r", encoding="utf-8") as file:
    helpdesk_data = json.load(file)


def read_request(state: HelpdeskState):
    message = state["message"].lower()

    has_wifi = "wifi" in message or "wi-fi" in message
    has_password = "password" in message

    if has_wifi and has_password:
        category = "both"
    elif has_wifi:
        category = "wifi"
    elif has_password:
        category = "password"
    else:
        category = "other"

    return {"category": category}


def wifi_help(state: HelpdeskState):
    instructions = helpdesk_data["instructions"]["wifi"]
    reply = "\n".join(instructions["steps"])

    return {"reply": reply}


def password_help(state: HelpdeskState):
    instructions = helpdesk_data["instructions"]["password"]
    reply = "\n".join(instructions["steps"])

    return {"reply": reply}


def other_help(state: HelpdeskState):
    return {
        "reply": "Is your problem related to Wi-Fi or a password?"
    }


def clarify_problem(state: HelpdeskState):
    return {
        "reply": (
            "Which problem would you like to solve first: "
            "connecting to Wi-Fi or recovering your password?"
        )
    }


def choose_next_node(state: HelpdeskState):
    return state["category"]


builder = StateGraph(HelpdeskState)

builder.add_node("read_request", read_request)
builder.add_node("wifi_help", wifi_help)
builder.add_node("password_help", password_help)
builder.add_node("other_help", other_help)
builder.add_node("clarify_problem", clarify_problem)

builder.add_edge(START, "read_request")

builder.add_conditional_edges(
    "read_request",
    choose_next_node,
    {
        "wifi": "wifi_help",
        "password": "password_help",
        "other": "other_help",
        "both": "clarify_problem"
    }
)

builder.add_edge("wifi_help", END)
builder.add_edge("password_help", END)
builder.add_edge("other_help", END)
builder.add_edge("clarify_problem", END)

graph = builder.compile()


test_messages = [
    "I cannot connect to Wi-Fi.",
    "I forgot my PASSWORD.",
    "My laptop screen is broken.",
    "My Wi-Fi password does not work."
]


for message in test_messages:
    print("\n" + "=" * 60)
    print("USER MESSAGE:", message)

    current_state = {"message": message}
    visited_nodes = []

    for event in graph.stream(
        current_state,
        stream_mode="updates"
    ):
        for node_name, update in event.items():
            visited_nodes.append(node_name)
            current_state.update(update)

            print("\nNODE:", node_name)
            print("UPDATE:", update)
            print("STATE AFTER NODE:", current_state)

    print("\nEXECUTION PATH:", " -> ".join(visited_nodes))
    print("FINAL REPLY:", current_state["reply"])
