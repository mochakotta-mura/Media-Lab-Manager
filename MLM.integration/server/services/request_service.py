"""Booking/request-management application service."""


class RequestService:
    def __init__(self, database, request_reader, availability_checker):
        self.db = database
        self.request_reader = request_reader
        self.ensure_available = availability_checker

    def create(self, data):
        self.ensure_available(data.get("equipmentIds", data.get("items", [])), data["pickupStartsAt"], data["returnEndsAt"])
        return self.db.create_request(data)

    def list(self, filters=None):
        filters = filters or {}
        return self.request_reader(filters)

    def approve(self, request_id, actor_id, notes=""):
        return self.db.approve_request(request_id, actor_id, notes)

    def reject(self, request_id, actor_id, reason=""):
        return self.db.reject_request(request_id, actor_id, reason)

    def cancel(self, request_id, actor_id):
        return self.db.cancel_request(request_id, actor_id)

    def schedule_window(self, data):
        return self.db.schedule_window(data)

    def request_extension(self, data):
        return self.db.request_extension(data)

    def pickup(self, data):
        return self.db.record_pickup(data)

    def return_equipment(self, data):
        return self.db.record_return(data)

    def damage(self, data):
        return self.db.record_damage(data)
