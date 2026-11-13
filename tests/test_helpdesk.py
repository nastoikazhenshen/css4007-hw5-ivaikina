
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import part1
import part2
from part3 import get_preference

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "message, expected",
    [
        ("I cannot connect to Wi-Fi.", "wifi"),
        ("I forgot my PASSWORD.", "password"),
        ("My laptop screen is broken.", "other"),
        ("My Wi-Fi password does not work.", "both"),
    ],
)
def test_routing(message, expected):
    result = part1.graph.invoke({"message": message})
    assert result["category"] == expected
    assert result["reply"]


def test_clarification_node():
    events = list(
        part1.graph.stream(
            {"message": "My Wi-Fi password does not work."},
            stream_mode="updates",
        )
    )

    assert "read_request" in events[0]
    assert "clarify_problem" in events[1]


def test_instruction_lookup():
    wifi = part2.lookup_instructions("wifi")
    password = part2.lookup_instructions("password")

    assert wifi["instruction_id"] == "GUIDE-WIFI"
    assert password["instruction_id"] == "GUIDE-PASSWORD"


@pytest.mark.parametrize(
    "profile, expected",
    [
        ("normal", "operational"),
        ("wifi_outage", "outage"),
        ("status_unavailable", "unknown"),
    ],
)
def test_wifi_status(profile, expected):
    result = part2.lookup_status("wifi", profile)
    assert result["status"] == expected


def test_password_recovery_status():
    result = part2.lookup_status(
        "account_recovery", "recovery_outage"
    )
    assert result["status"] == "outage"


def test_ticket_creation(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "data", tmp_path / "data")
    monkeypatch.setattr(part2, "ROOT", tmp_path)

    result = part2.save_ticket(
        "Cannot connect to Wi-Fi",
        ["enabled Wi-Fi", "tried reconnecting"],
        "demo-user-a",
        "test-thread",
        "normal",
        "operational",
    )

    assert result["status"] == "draft"
    assert result["sent"] is False

    ticket = json.loads(
        Path(result["file"]).read_text(encoding="utf-8")
    )

    assert ticket["user_id"] == "demo-user-a"
    assert ticket["steps_tried"] == [
        "enabled Wi-Fi",
        "tried reconnecting",
    ]


def test_ticket_requires_details(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "data", tmp_path / "data")
    monkeypatch.setattr(part2, "ROOT", tmp_path)

    result = part2.save_ticket(
        "Wi-Fi connection fails",
        [],
        "demo-user-a",
        "test-thread",
        "normal",
        "not_checked",
    )

    assert "error" in result


def run_memory(message, user_id, thread_id, storage):
    command = [
        sys.executable,
        str(ROOT / "part3.py"),
        "chat",
        "--mode", "fake",
        "--storage", str(storage),
        "--user-id", user_id,
        "--thread-id", thread_id,
        "--message", message,
    ]

    environment = os.environ.copy()
    environment.pop("OPENAI_API_KEY", None)

    process = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )

    return json.loads(process.stdout)



def test_memory_after_restart(tmp_path):
    storage = tmp_path / "memory"

    first = run_memory(
        "My issue is Wi-Fi. I enabled it and tried reconnecting.",
        "demo-user-a",
        "same-thread",
        storage,
    )

    second = run_memory(
        "Which steps did I already try?",
        "demo-user-a",
        "same-thread",
        storage,
    )

    assert first["process_id"] != second["process_id"]
    assert "enabled it" in second["saved_steps"]
    assert "tried reconnecting" in second["saved_steps"]
    assert "wi-fi" in second["saved_problem"].lower()


def test_user_memory_isolation(tmp_path):
    storage = tmp_path / "memory"

    run_memory(
        "Please remember that I prefer replies in Kazakh. "
        "I have a Wi-Fi problem.",
        "demo-user-a",
        "thread-a1",
        storage,
    )

    same_user = run_memory(
        "Which language did I ask you to use?",
        "demo-user-a",
        "thread-a2",
        storage,
    )

    other_user = run_memory(
        "Have I told you a preferred language "
        "or a previous problem?",
        "demo-user-b",
        "thread-b1",
        storage,
    )

    assert get_preference(storage, "demo-user-a") == "Kazakh"
    assert same_user["saved_preference"] == "Kazakh"
    assert same_user["saved_problem"] == ""

    assert other_user["saved_preference"] is None
    assert other_user["saved_problem"] == ""
    assert get_preference(storage, "demo-user-b") is None
