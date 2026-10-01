"""Equipment-management application service.

This module is the boundary between HTTP routes and inventory operations.
Persistence remains in the shared Database facade.
"""


class EquipmentService:
    def __init__(self, database):
        self.db = database

    def list_units(self, filters=None):
        return self.db.find(filters or {})

    def list_catalog(self, filters=None):
        return self.db.get_listings(filters or {})

    def stats(self):
        return self.db.stats()

    def add_unit(self, data):
        return self.db.add_equipment(data)

    def update_unit(self, equipment_id, data, actor_id):
        return self.db.update_equipment(equipment_id, data, actor_id)

    def list_damage_reports(self, filters=None):
        return self.db.list_damage_reports(filters or {})
