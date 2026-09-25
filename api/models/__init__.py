"""Import every model module so Base.metadata is complete for Alembic and create_all."""
from api.db.base import Base
from api.models.correlation import Campaign, Incident, IncidentEdge, IncidentEvent
from api.models.detection import ConfigVersion, Signal, UserDayScore
from api.models.evaluation import GroundTruth
from api.models.explain import Attribution, Narrative
from api.models.feedback import Review, Suppression
from api.models.features import UserDayFeature
from api.models.identity import Account, AuditLog, SessionToken, User, UserOrg
from api.models.ingest import Event, IngestRun

__all__ = [
    "Base",
    "User",
    "UserOrg",
    "Account",
    "SessionToken",
    "AuditLog",
    "IngestRun",
    "Event",
    "UserDayFeature",
    "ConfigVersion",
    "Signal",
    "UserDayScore",
    "Campaign",
    "Incident",
    "IncidentEvent",
    "IncidentEdge",
    "Narrative",
    "Attribution",
    "Review",
    "Suppression",
    "GroundTruth",
]
