"""Notification and integration-event application service.

The current implementation stores audit/outbox events. A future email, SMS,
or in-app delivery worker can consume this service without changing routes.
"""


class NotificationService:
    def __init__(self, database):
        self.db = database

    def dashboard(self):
        return self.db.get_dashboard()

    def pending_events(self, limit=100):
        return self.db.get_outbox(limit)

    def mark_published(self, event_ids):
        return self.db.mark_events_published(event_ids)

    def audit_history(self, entity_type, entity_id):
        return self.db.get_audit_history(entity_type, entity_id)
