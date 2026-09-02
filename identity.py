"""Managed Deep Agents identity: who is calling, and which threads and credentials they own.

Ingress channels such as Slack need an explicit identity declaration so each caller gets private
threads. LangSmith API-key auth is the simplest documented option; swap in `auth.supabase(...)` for
end-user sign-in. Approval authority is not granted here: approvers are still the host-owned
`PAID_MEDIA_APPROVER_IDS` list.
"""

from managed_deepagents import auth, define_identity

identity = define_identity(auth=auth.langsmith_api_key())
