
import json
from pathlib import Path
from typing import TypedDict

from langgraph.graph import StateGraph, START, END


# 1. Define the graph state
class HelpdeskState(TypedDict, total=False):
    message: str
    category: str
    reply: str


# 2. Load instructions from the teacher's JSON file
DATA_PATH = Path(__file__).parent / "data" / "helpdesk.json"

with open(DATA_PATH, "r", encoding="utf-8") as file:
    helpdesk_data = json.load(file)


# 3. Node: identify the request category
def read_request(state: HelpdeskState):
    message = state["message"].lower()

    if "wifi" in message or "wi-fi" in message:
        category = "wifi"
    elif "password" in message:
        category = "password"
    else:
        category = "other"

    return {"category": category}


# 4. Node: provide Wi-Fi instructions
def wifi_help(state: HelpdeskState):
    instructions = helpdesk_data["instructions"]["wifi"]
    reply = "\n".join(instructions["steps"])

    return {"reply": reply}


# 5. Node: provide password instructions
def password_help(state: HelpdeskState):
    instructions = helpdesk_data["instructions"]["password"]
    reply = "\n".join(instructions["steps"])

    return {"reply": reply}


# 6. Node: handle other questions
def other_help(state: HelpdeskState):
    return {
        "reply": "Is your problem related to Wi-Fi or a password?"
    }


# 7. Conditional routing function
def choose_next_node(state: HelpdeskState):
    return state["category"]


# 8. Build the graph
builder = StateGraph(HelpdeskState)

builder.add_node("read_request", read_request)
builder.add_node("wifi_help", wifi_help)
builder.add_node("password_help", password_help)
builder.add_node("other_help", other_help)

builder.add_edge(START, "read_request")

builder.add_conditional_edges(
    "read_request",
    choose_next_node,
    {
        "wifi": "wifi_help",
        "password": "password_help",
        "other": "other_help"
    }
)

builder.add_edge("wifi_help", END)
builder.add_edge("password_help", END)
builder.add_edge("other_help", END)

graph = builder.compile()


# 9. Test all four requests and record execution traces
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
        current_state, stream_mode="updates"
    ):
        for node_name, update in event.items():
            visited_nodes.append(node_name)
            current_state.update(update)

            print("\nNODE:", node_name)
            print("UPDATE:", update)
            print("STATE AFTER NODE:", current_state)

    print("\nEXECUTION PATH:", " -> ".join(visited_nodes))
    print("FINAL REPLY:", current_state["reply"])
