"""Managed Deep Agents schedule: daily housekeeping (`middleware/housekeeping.py`).

It deletes the agent's expired check-ins, then ends in code before any model call. It reads no
account, calls no provider, and posts nothing.
"""

from managed_deepagents import define_schedule

schedule = define_schedule(cron="30 5 * * *", timezone="UTC", prompt="<housekeeping>")
