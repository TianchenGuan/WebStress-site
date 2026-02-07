"""Shared fixtures for LLMOS tests."""

import copy
import pytest


@pytest.fixture
def sample_ui_tree():
    """A sample UI tree for testing."""
    return {
        "bid": "root",
        "tag": "desktop",
        "role": "application",
        "visible": True,
        "bounds": {"x": 0, "y": 0, "width": 1920, "height": 1080},
        "children": [
            {
                "bid": "taskbar",
                "tag": "div",
                "role": "toolbar",
                "visible": True,
                "bounds": {"x": 0, "y": 1040, "width": 1920, "height": 40},
                "children": [
                    {
                        "bid": "start_btn",
                        "tag": "button",
                        "role": "button",
                        "text": "Start",
                        "visible": True,
                        "bounds": {"x": 0, "y": 1040, "width": 80, "height": 40},
                    },
                ],
            },
            {
                "bid": "window1",
                "tag": "window",
                "role": "window",
                "text": "File Explorer",
                "visible": True,
                "state": "normal",
                "bounds": {"x": 100, "y": 50, "width": 800, "height": 600},
                "current_path": "/home/user/Documents",
                "children": [
                    {
                        "bid": "title_bar",
                        "tag": "div",
                        "role": "toolbar",
                        "visible": True,
                        "children": [
                            {
                                "bid": "close_btn",
                                "tag": "button",
                                "role": "button",
                                "text": "X",
                                "visible": True,
                            },
                            {
                                "bid": "min_btn",
                                "tag": "button",
                                "role": "button",
                                "text": "_",
                                "visible": True,
                            },
                        ],
                    },
                    {
                        "bid": "content_area",
                        "tag": "div",
                        "role": "main",
                        "visible": True,
                        "children": [
                            {
                                "bid": "file1",
                                "tag": "div",
                                "role": "listitem",
                                "text": "readme.txt",
                                "visible": True,
                            },
                            {
                                "bid": "file2",
                                "tag": "div",
                                "role": "listitem",
                                "text": "notes.md",
                                "visible": True,
                            },
                        ],
                    },
                ],
            },
            {
                "bid": "hidden_widget",
                "tag": "div",
                "visible": False,
                "text": "I am hidden",
            },
            {
                "bid": "minimized_window",
                "tag": "window",
                "role": "window",
                "text": "Calculator",
                "visible": True,
                "state": "minimized",
                "children": [
                    {
                        "bid": "calc_display",
                        "tag": "input",
                        "role": "textbox",
                        "value": "42",
                        "visible": True,
                    },
                ],
            },
        ],
    }


@pytest.fixture
def sample_state(sample_ui_tree):
    """A complete sample state including meta, filesystem, hidden_state."""
    return {
        "meta": {
            "tick": 5,
            "status": "running",
            "random_seed": 42,
        },
        "ui": sample_ui_tree,
        "filesystem": {
            "/home/user/Documents/readme.txt": {
                "type": "file",
                "visible": True,
                "content": "Hello world",
            },
            "/home/user/Documents/notes.md": {
                "type": "file",
                "visible": True,
                "content": "Some notes",
            },
            "/home/user/.secrets": {
                "type": "file",
                "visible": False,
                "content": "secret data",
            },
        },
        "hidden_state": {
            "form_submitted": False,
            "login_count": 3,
        },
    }


@pytest.fixture
def sample_state_copy(sample_state):
    """A deep copy of sample_state for mutation tests."""
    return copy.deepcopy(sample_state)
