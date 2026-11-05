# Background work and progress

Long work should not hold a person's Slack thread, and a person should see what the agent is doing
while it works. Both use public Managed Deep Agents 0.10 APIs. Nothing here adds a write path.

## Background helpers

`src/paid_media_agent/subagents.py` defines three helper specs. `agent.py` declares each as an
async subagent, with the literal `name` and `"async": True` after the spread so `mda build` reads
them without running code:

| Helper | For | Tools |
| --- | --- | --- |
| `account-puller` | pulls and comparisons across many accounts or long windows | `list_accounts`, `discover_tools`, platform reads, `compare_periods`, `summarize_window` |
| `report-builder` | a full rendered report | the same, plus `render_report` |
| `general-purpose` | other read-only research | the same as `report-builder` |

MDA builds each as its own graph on the deployment (`paid-media-agent--account-puller`, ...). The
lead starts one with `start_async_task` and ends its turn. The helper runs in the lead's sandbox and
trace. When it finishes, deepagents' `notify_parent` starts a run on the lead's thread if the thread
is idle (never on a thread waiting for an approval), and MDA posts that run's answer to the thread's
origin, the Slack thread the request came from. A helper's run is an Agent Server run with its own
checkpointed thread, so it outlives the lead's turn without a hand-built waker or transcript store.

Read-only is enforced in code:

- A helper's tools are listed explicitly. It gets no proposal, execution, check-in, or async-task
  tool. MDA would otherwise inherit the lead's tools for a helper that leaves `tools` unset.
- An async subagent does not inherit the lead's middleware, so each helper gets its own copy of
  the guard stack from `assembly.py`: retry, timeout, and call limit; today's date; tool selection;
  the invocation guard (filesystem reads plus its own tools; `task`, `execute`, and `delete`
  hidden); result offload; redaction; and the cost meter.
- `general-purpose` is declared because MDA otherwise adds a background copy of the default
  general-purpose subagent with every lead tool and none of its middleware.

Any caller allowed to start runs on the deployment can run a helper graph directly. It can only read.

Local and self-hosted runs have no Agent Server to launch helper graphs on, so `managed=False`
leaves helpers out and the lead does long work in its own turn. `task` stays hidden everywhere.

## Check-ins

`tools/check_ins.py` binds `schedule_check_in` and `cancel_check_in` on MDA only. A check-in is a
one-time runtime schedule on the current thread (`runtime.schedules.create(at=...,
new_thread=False)`) with a note the agent writes for itself. It survives redeploys and answers in
the thread's origin. It is agent-owned on a channel thread (MDA requires a channel for that) and
user-owned otherwise, and carries `metadata={"paid_media_agent": "check-in"}`. Cancel reaches only
this thread's check-ins. A check-in run is an ordinary run under the same approval policy.

`schedules/housekeeping.py` runs daily with the prompt `<housekeeping>`.
`middleware/housekeeping.py`, first in the lead's middleware, recognizes it in `before_agent`,
deletes expired check-ins that carry the metadata key, and ends the run before any model call.

## Slack progress

`surfaces/progress.py` is a deterministic phrasebook: every tool call reads as an analyst's step
in two tenses ("Reading Google Ads campaign performance" / "Read Google Ads campaign performance").
Platform reads are parsed from `<platform>__<operation>`, file tools from their path (a wiki page is
"the wiki on bidding and budget"), and a helper launch from its type. A phrase never carries
argument text.

- On MDA, `channels/slack.py` passes `plan_from_state` as the channel's `status`. MDA calls it with
  the agent's state as the run starts, around each model call, and every few seconds while a call
  runs, and Slack shows the current turn's steps as a plan above the reply. `status` is
  experimental in MDA 0.10; a failing chooser leaves Slack's default status and never slows the run.
- Self-hosted Slack streams the same phrases as native `task_update` chunks.

## Footer and meter

`middleware/meter.py` prices every model call from its `usage_metadata` with the list prices in
`middleware/prices.toml` (cache reads and writes priced apart) and writes the total to the LangGraph
store under the conversation's thread. Each run writes only its own key. On MDA a helper's
`runtime.thread` is its lead's thread, so helper spend lands in the lead's conversation. Without a
store the meter keeps an in-memory one. An unlisted model counts as unpriced and the footer then
omits the cost.

`middleware/footer.py` starts a job when a person's message starts a run (not a helper
notification or housekeeping) and appends one line to the final reply of a Slack turn that did work:
helpers still running, minutes since the request, and the estimated cost since it, for example
`_1 helper running · 3 min · ~$0.12 so far_`. The line is part of the reply, so it costs no extra
notification, and it is cut from earlier replies before each model call. An exact `[quiet]` reply
gets none.
