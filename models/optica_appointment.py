
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


    @api.model
    def _google_fetch_events(self):
        """Ejecuta el lector de Google Calendar en su entorno virtual."""
        script_path = (
            Path(__file__).resolve().parent.parent
            / "scripts"
            / "read_google_calendar.py"
        )

        result = subprocess.run(
            [
                "/opt/odoo/google-venv/bin/python",
                str(script_path),
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=True,
        )

        events = json.loads(result.stdout)

        if not isinstance(events, list):
            raise ValueError(
                "Google Calendar no devolvió una lista de eventos."
            )

        _logger.info(
            "Google Calendar: %s eventos recibidos",
            len(events),
        )

        return events

    
    
    @api.model
    def _google_extract_customer_data(self, event):
        """Extrae los datos del paciente de una reserva de Meta."""
        description = event.get("description") or ""
        data = {}

        for line in description.splitlines():
            line = line.strip()

            if ":" not in line:
                continue

            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()

            if key == "customer name":
                data["patient_name"] = value

            elif key == "customer phone":
                data["whatsapp"] = value

            elif key == "booking notes":
                data["reason"] = value

            elif key in ("promotion", "promo"):
                data["promotion"] = value

        excluded_emails = {
            "hhvida@gmail.com",
            "odoo-appointment@gtm-pd63jjjm-ztczy.iam.gserviceaccount.com",
        }

        customer_emails = []

        for attendee in event.get("attendees", []):
            email = (attendee.get("email") or "").strip().lower()

            if (
                email
                and "@" in email
                and email not in excluded_emails
                and not attendee.get("self", False)
                and not attendee.get("organizer", False)
            ):
                customer_emails.append(email)

        customer_emails = list(set(customer_emails))

        if len(customer_emails) == 1:
            data["email"] = customer_emails[0]

        return data

    
    @api.model
    def _google_import_event(self, event):
        """Importa una reserva del agente como cita pendiente."""
        event_id = event.get("id")
        if not event_id:
            return False

        existing = self.search([
            ("google_event_id", "=", event_id),
        ], limit=1)

        if existing:
            return existing

        data = self._google_extract_customer_data(event)

        required = ("patient_name", "whatsapp", "email")
        missing = [key for key in required if not data.get(key)]

        if missing:
            _logger.warning(
                "Google Calendar: evento %s omitido; faltan datos: %s",
                event_id,
                ", ".join(missing),
            )
            return False

        start_value = event.get("start", {}).get("dateTime")
        end_value = event.get("end", {}).get("dateTime")

        if not start_value or not end_value:
            return False

        start_dt = datetime.fromisoformat(
            start_value.replace("Z", "+00:00")
        )
        end_dt = datetime.fromisoformat(
            end_value.replace("Z", "+00:00")
        )

        if start_dt.tzinfo is None or end_dt.tzinfo is None:
            _logger.warning(
                "Google Calendar: evento %s sin zona horaria",
                event_id,
            )
            return False

        local_tz = pytz.timezone("America/Mexico_City")
        local_start = start_dt.astimezone(local_tz)
        duration = (end_dt - start_dt).total_seconds() / 3600

        if duration <= 0:
            return False

        
        if (
            local_start.second
            or local_start.microsecond
            or local_start.date()
            != end_dt.astimezone(local_tz).date()
        ):
            _logger.warning(
                "Google Calendar: evento %s con horario no compatible",
                event_id,
            )
            return False

        appointment_time = (
            local_start.hour + local_start.minute / 60.0
        )


        values = {
            "patient_name": data["patient_name"],
            "whatsapp": data["whatsapp"],
            "phone": data["whatsapp"],
            "email": data["email"],
            "appointment_date": local_start.date(),
            "appointment_time": appointment_time,
            "duration": duration,
            "appointment_type": "exam",
            "appointment_origin": "whatsapp_bot",
            "google_event_id": event_id,
            "reason": data.get("reason") or event.get("summary") or "",
            "state": "draft",
        }

        appointment = self.create(values)

        _logger.info(
            "Google Calendar: cita %s importada desde evento %s",
            appointment.id,
            event_id,
        )

        return appointment

    
    @api.model
    def _google_sync_appointments(self):
        """Sincroniza reservas de Google Calendar con Odoo."""
        events = self._google_fetch_events()

        imported = 0
        skipped = 0
        errors = 0

        for event in events:
            event_id = event.get("id", "sin_id")

            try:
                # Cada evento se procesa de manera independiente.
                # Si uno falla, no afecta a los demás.
                with self.env.cr.savepoint():
                    existing = self.search([
                        ("google_event_id", "=", event_id),
                    ], limit=1)

                    if existing:
                        skipped += 1
                        continue

                    appointment = self._google_import_event(event)

                    if appointment:
                        imported += 1
                    else:
                        skipped += 1

            except Exception:
                errors += 1
                _logger.exception(
                    "Google Calendar: error importando evento %s",
                    event_id,
                )

        _logger.info(
            "Google Calendar: sincronización terminada. "
            "Importadas=%s, Omitidas=%s, Errores=%s",
            imported,
            skipped,
            errors,
        )

        return True


