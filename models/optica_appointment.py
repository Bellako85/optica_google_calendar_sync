
# -*- coding: utf-8 -*-

from odoo import models


class OpticaAppointment(models.Model):
    _inherit = "optica.appointment"

    _sql_constraints = [
        (
            "google_event_id_unique",
            "unique(google_event_id)",
            "Esta reserva de Google Calendar ya fue importada.",
        ),
    ]
