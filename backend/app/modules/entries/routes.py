from fastapi import APIRouter

from app.modules.entries.controller import (
    create_past_entry,
    create_text_entry,
    create_voice_entry,
    discard_draft,
    get_draft,
    get_entry_detail,
    list_entries,
    retry_entry,
    save_draft,
)
from app.modules.entries.schemas import EntryDetail, EntryDraftResponse, EntryPage, PastEntryAccepted
from app.shared.http.protected_route import ProtectedAPIRoute


router = APIRouter(route_class=ProtectedAPIRoute)
router.add_api_route("/entry/draft", get_draft, methods=["GET"], response_model=EntryDraftResponse)
router.add_api_route("/entry/draft", save_draft, methods=["PUT"], response_model=EntryDraftResponse)
router.add_api_route("/entry/draft", discard_draft, methods=["DELETE"], response_model=EntryDraftResponse)
router.add_api_route("/entry", create_text_entry, methods=["POST"], response_model=EntryDetail, status_code=201)
router.add_api_route("/entries", list_entries, methods=["GET"], response_model=EntryPage)
router.add_api_route("/past-entries", create_past_entry, methods=["POST"], response_model=PastEntryAccepted, status_code=202)
router.add_api_route("/entries/voice", create_voice_entry, methods=["POST"], response_model=EntryDetail, status_code=201)
router.add_api_route("/entries/{entry_id}", get_entry_detail, methods=["GET"], response_model=EntryDetail)
router.add_api_route("/entries/{entry_id}/retry", retry_entry, methods=["POST"], response_model=EntryDetail)
