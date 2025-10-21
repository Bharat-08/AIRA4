from fastapi import APIRouter, Depends
from ..security.deps import require_user

router = APIRouter(tags=["me"])

@router.get("/me")
def get_me(ctx=Depends(require_user)):
    u = ctx["user"]; m = ctx["membership"]
    return {
        "id": str(u.id),
        "email": u.email,
        "name": u.name,
        "avatar_url": u.avatar_url,
        "is_superadmin": u.is_superadmin,
        "org_id": str(m.org_id),
        "role": m.role,
    }
