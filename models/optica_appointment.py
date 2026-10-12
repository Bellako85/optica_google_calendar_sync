
# -*- coding: utf-8 -*-

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path

import pytz

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class OpticaAppointment(models.Model):
    _inherit = "optica.appointment"

    _sql_constraints = [
        (
            "google_event_id_unique",
            "unique(google_event_id)",
            "Esta reserva de Google Calendar ya fue importada.",
        ),
    ]
