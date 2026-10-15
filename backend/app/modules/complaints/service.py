from datetime import UTC, datetime

from app.models import AppUser, Complaint


def set_verified(complaint: Complaint, verified: bool, user: AppUser, now: datetime | None = None) -> None:
    """Mark a complaint as checked by `user`, or take the mark back. Only a change touches `verified_by/at`:
    saving an already verified complaint again keeps who verified it and when."""
    if verified == complaint.is_verified:
        return
    complaint.is_verified = verified
    complaint.verified_by = user.id if verified else None
    complaint.verified_at = (now or datetime.now(UTC)) if verified else None
