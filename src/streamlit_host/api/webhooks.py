import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import App, AppState, PendingAction

log = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/apps/{app_id}/{token}", status_code=202)
def git_push_webhook(app_id: str, token: str, db: Session = Depends(get_db)):
    """Generic push webhook: any POST with the correct per-app token triggers a redeploy.

    Works as the target of GitHub/GitLab/Gitea push webhooks (payload is ignored;
    the tracked branch head is re-resolved at build time).
    """
    app = db.get(App, app_id)
    if app is None or not hmac.compare_digest(app.webhook_token, token):
        raise HTTPException(404, "not found")
    if app.state == AppState.building or app.pending_action == PendingAction.delete:
        return {"status": "ignored (build in progress or app deleting)"}
    app.pending_action = PendingAction.deploy
    log.info("webhook triggered redeploy for app %s", app.slug)
    return {"status": "deploy scheduled"}
