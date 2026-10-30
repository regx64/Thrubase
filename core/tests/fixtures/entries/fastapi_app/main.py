from fastapi import APIRouter, FastAPI

api = FastAPI()
router = APIRouter()


@api.get("/")
async def root() -> dict:
    return {}


@router.post("/items")
async def create_item() -> dict:
    return {}


@api.on_event("startup")
def not_a_route() -> None:
    pass
