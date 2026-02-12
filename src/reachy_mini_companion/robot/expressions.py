"""Expression choreography data for Reachy Mini."""

from __future__ import annotations

# Each expression is a list of movement steps.
# Each step defines: head_pose (roll, pitch, yaw in degrees), antennas [right, left],
# body_yaw, and duration in seconds.
# Antennas: 0.0 = flat, -30 = forward/perked, 30 = back/drooped
# Body yaw: rotation in degrees

EXPRESSIONS: dict[str, list[dict]] = {
    "nod": [
        {"head_pose": {"pitch": -15}, "antennas": [-10, -10], "body_yaw": 0, "duration": 0.3},
        {"head_pose": {"pitch": 10}, "antennas": [-10, -10], "body_yaw": 0, "duration": 0.3},
        {"head_pose": {"pitch": -10}, "antennas": [-10, -10], "body_yaw": 0, "duration": 0.25},
        {"head_pose": {"pitch": 0}, "antennas": [0, 0], "body_yaw": 0, "duration": 0.3},
    ],
    "shake_head": [
        {"head_pose": {"yaw": -20}, "antennas": [0, 0], "body_yaw": 0, "duration": 0.25},
        {"head_pose": {"yaw": 20}, "antennas": [0, 0], "body_yaw": 0, "duration": 0.25},
        {"head_pose": {"yaw": -15}, "antennas": [0, 0], "body_yaw": 0, "duration": 0.2},
        {"head_pose": {"yaw": 0}, "antennas": [0, 0], "body_yaw": 0, "duration": 0.25},
    ],
    "tilt_curious": [
        {"head_pose": {"roll": 20, "pitch": -5}, "antennas": [-25, -15], "body_yaw": 0, "duration": 0.5},
        {"head_pose": {"roll": 0, "pitch": 0}, "antennas": [0, 0], "body_yaw": 0, "duration": 0.5},
    ],
    "wiggle_antenna_happy": [
        {"head_pose": {}, "antennas": [-30, -30], "body_yaw": 0, "duration": 0.2},
        {"head_pose": {}, "antennas": [10, 10], "body_yaw": 0, "duration": 0.2},
        {"head_pose": {}, "antennas": [-30, -30], "body_yaw": 0, "duration": 0.2},
        {"head_pose": {}, "antennas": [10, 10], "body_yaw": 0, "duration": 0.2},
        {"head_pose": {}, "antennas": [0, 0], "body_yaw": 0, "duration": 0.2},
    ],
    "look_away_shy": [
        {"head_pose": {"yaw": 30, "pitch": 10, "roll": -5}, "antennas": [15, 15], "body_yaw": 10, "duration": 0.6},
        {"head_pose": {"yaw": 15, "pitch": 5}, "antennas": [5, 5], "body_yaw": 5, "duration": 0.5},
        {"head_pose": {"yaw": 0, "pitch": 0}, "antennas": [0, 0], "body_yaw": 0, "duration": 0.5},
    ],
    "surprise": [
        {"head_pose": {"pitch": -15}, "antennas": [-30, -30], "body_yaw": 0, "duration": 0.2},
        {"head_pose": {"pitch": -10}, "antennas": [-30, -30], "body_yaw": 0, "duration": 0.5},
        {"head_pose": {"pitch": 0}, "antennas": [0, 0], "body_yaw": 0, "duration": 0.4},
    ],
    "thinking": [
        {"head_pose": {"roll": 10, "pitch": -10, "yaw": 15}, "antennas": [-5, -20], "body_yaw": 0, "duration": 0.5},
        {"head_pose": {"roll": 10, "pitch": -10, "yaw": 15}, "antennas": [-5, -20], "body_yaw": 0, "duration": 1.0},
        {"head_pose": {"roll": 0, "pitch": 0, "yaw": 0}, "antennas": [0, 0], "body_yaw": 0, "duration": 0.4},
    ],
    "sad": [
        {"head_pose": {"pitch": 20}, "antennas": [20, 20], "body_yaw": 0, "duration": 0.6},
        {"head_pose": {"pitch": 15}, "antennas": [15, 15], "body_yaw": 0, "duration": 0.8},
        {"head_pose": {"pitch": 0}, "antennas": [0, 0], "body_yaw": 0, "duration": 0.5},
    ],
    "excited": [
        {"head_pose": {"pitch": -10}, "antennas": [-30, -30], "body_yaw": -5, "duration": 0.2},
        {"head_pose": {"pitch": -5}, "antennas": [-30, -30], "body_yaw": 5, "duration": 0.2},
        {"head_pose": {"pitch": -10}, "antennas": [-30, -30], "body_yaw": -5, "duration": 0.2},
        {"head_pose": {"pitch": -5}, "antennas": [-30, -30], "body_yaw": 5, "duration": 0.2},
        {"head_pose": {"pitch": 0}, "antennas": [0, 0], "body_yaw": 0, "duration": 0.3},
    ],
}

# Head directions for robot_look_at tool
LOOK_DIRECTIONS: dict[str, dict] = {
    "left": {"yaw": 30},
    "right": {"yaw": -30},
    "up": {"pitch": -20},
    "down": {"pitch": 20},
    "center": {"yaw": 0, "pitch": 0, "roll": 0},
    "user": {"yaw": 0, "pitch": -5},  # Slightly look up at user
}
