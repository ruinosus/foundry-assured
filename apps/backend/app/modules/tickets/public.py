"""Ticket creation and persistence — the module's entire public surface.

`create_ticket` is the write that RULE #5 protects: it may only run after explicit human
approval, and the approver must hold Approver or Admin. That gate lives at the call site
(`helpdesk`'s escalation response handler), not here — this module persists, it does not
authorize.
"""

from app.modules.tickets.internal.tickets import create_ticket, list_tickets

__all__ = ["create_ticket", "list_tickets"]
