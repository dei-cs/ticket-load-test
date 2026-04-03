from fastapi import APIRouter, HTTPException
from models.user import User
from data.query_user import populate_user_table, get_users, delete_all_users_query

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/generate")
def generate_user_batch(count: int):
    populate_user_table(count)
    return {"inserted": count}

@router.get("/get", response_model=list[User])
def get_user_batch(count: int, starting_index: int = 0):
    return get_users(count, starting_index)

@router.delete("/delete")
def delete_all_users():
    delete_count = delete_all_users_query()
    return {"deleted": delete_count}