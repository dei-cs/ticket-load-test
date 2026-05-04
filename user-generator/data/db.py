from peewee import *
from pathlib import Path

DB_PATH = Path("/app/db-data/user_database.db")
db = SqliteDatabase(DB_PATH)

class BaseModel(Model):
    class Meta:
        database = db


class User(BaseModel):
    id = AutoField()
    user_id = TextField(unique=True)
    name = TextField()
    email = TextField()