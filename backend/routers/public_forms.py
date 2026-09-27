"""routers/public_forms.py — formulir publik yang BENAR-BENAR tersimpan (audit butir 9).

POST /api/contact     {name, email, subject?, message}  -> {ok: true, id}
POST /api/newsletter  {email}                            -> {ok: true, subscribed: true}  (idempoten)
GET  /api/admin/contact-messages                         -> [Message]  (admin, 200 terbaru)
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field

from core_utils import new_id, now_iso, safe_doc
from db import get_db
from dependencies import require_role

router = APIRouter(tags=["forms"])
LIST_MAX = 200


class ContactInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    subject: Optional[str] = Field(default="", max_length=200)
    message: str = Field(min_length=1, max_length=5000)


class NewsletterInput(BaseModel):
    email: EmailStr


@router.post("/contact")
async def submit_contact(payload: ContactInput):
    doc = {"id": new_id("msg"), **payload.model_dump(), "status": "new", "created_at": now_iso()}
    await get_db().contact_messages.insert_one(dict(doc))
    return {"ok": True, "id": doc["id"]}


@router.post("/newsletter")
async def subscribe(payload: NewsletterInput):
    email = payload.email.lower()
    await get_db().newsletter_subscribers.update_one(
        {"email": email},
        {"$set": {"status": "subscribed", "updated_at": now_iso()},
         "$setOnInsert": {"id": new_id("nws"), "email": email, "created_at": now_iso()}},
        upsert=True)
    return {"ok": True, "subscribed": True}


@router.get("/admin/contact-messages", dependencies=[Depends(require_role("admin"))])
async def list_contact_messages():
    docs = await get_db().contact_messages.find({}).sort([("created_at", -1)]).to_list(LIST_MAX)
    return [safe_doc(d) for d in docs]
