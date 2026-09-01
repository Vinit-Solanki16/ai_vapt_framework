"""Mentor-facing prototype: CLI + trace around the real decision engine.

All engine logic is delegated to decision_engine.core.engine.run_engine().
No reimplementation of ranking, pivot, or termination — those are engine-native.
"""

__version__ = "0.1.0"
__engine_version__ = 1
