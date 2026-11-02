"""Shared constants for the DMD body-view domain adaptation.

The class mapping is the one the zero-shot evaluation already used
(`FYP2-DMD-zero-shot/manifests/label_mapping.json`); the split is subject-level so no
frame from a test subject can reach training, and every split keeps `c7`
(`reach_backseat`) because that action only appears in each subject's s3 session.
"""
from __future__ import annotations

ACTION_TO_CLASS = {
    "safe_drive": "c0",
    "texting_right": "c1",
    "phonecall_right": "c2",
    "texting_left": "c3",
    "phonecall_left": "c4",
    "radio": "c5",
    "drinking": "c6",
    "reach_backseat": "c7",
    "hair_and_makeup": "c8",
    "talking_to_passenger": "c9",
}

EXCLUDED_ACTIONS = frozenset(
    {"reach_side", "unclassified", "change_gear", "standstill_or_waiting"})

SPLITS = {
    "train": ("gA_1", "gA_5", "gB_6"),
    "val": ("gB_10",),
    "test": ("gC_13", "gE_29"),
}

CLASS_IDS = tuple(f"c{i}" for i in range(10))
CLASS_NAMES = (
    "safe_driving", "texting_right", "talking_phone_right", "texting_left",
    "talking_phone_left", "operating_radio", "drinking", "reaching_behind",
    "hair_makeup", "talking_to_passenger",
)


def subject_of(session_name: str) -> str:
    """``gA_5_s1_2019-03-08T10;57;00+01;00`` -> ``gA_5``."""
    return "_".join(session_name.split("_")[:2])


def class_of(action: str) -> str | None:
    """The runtime class id for a DMD driver action, or None when it is excluded."""
    return ACTION_TO_CLASS.get(action)


def split_of(subject: str) -> str:
    for name, subjects in SPLITS.items():
        if subject in subjects:
            return name
    raise KeyError(f"subject {subject!r} is not in the split table")
