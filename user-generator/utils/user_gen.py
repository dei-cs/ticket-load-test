from uuid import uuid4
from faker import Faker
from data.db import User

fake = Faker()

def generate_user() -> User:
    return {
        "user_id": str(uuid4()),
        "name": fake.name(),
        "email": fake.email(),
    }